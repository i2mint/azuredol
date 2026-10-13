"""Key-transform blindness (i2mint/azuredol#4): wrapped stores over a mocked SDK (no Azurite)."""

from unittest.mock import MagicMock

import pytest
from azure.storage.blob import ContainerClient
from dol import KeyCodecs, Pipe, filt_iter

from azuredol import (
    AccountStore,
    AzureJsonStore,
    AzurePickleStore,
    AzureTextStore,
    ContainerNotEmptyError,
    ContainerNotFoundError,
    ContainerStore,
    delete_container,
    walk_container,
)


class FakeBlob:
    def __init__(self, name):
        self.name = name


class FakeContainer(MagicMock):
    """Enough of a ContainerClient for list/walk/exists/get_blob_client."""


def mk_container(name="c", blobs=()):
    cc = MagicMock(spec=ContainerClient)
    cc.container_name = name
    cc.blobs = dict(blobs)
    cc.exists.return_value = True
    cc.list_blobs.side_effect = lambda name_starts_with="", **kw: (
        FakeBlob(n) for n in list(cc.blobs) if n.startswith(name_starts_with or "")
    )
    cc.delete_blob.side_effect = lambda n: cc.blobs.pop(n)
    cc.walk_blobs.side_effect = lambda name_starts_with="", delimiter="/": iter(
        [("walk", name_starts_with, delimiter)]
    )

    def get_blob_client(blob):
        bc = MagicMock()
        bc.exists.side_effect = lambda: blob in cc.blobs
        bc.download_blob.side_effect = lambda **kw: MagicMock(
            readall=lambda: cc.blobs[blob]
        )
        return bc

    cc.get_blob_client.side_effect = get_blob_client
    return cc


# ---- 1. typed stores keep the trailing-slash sub-store -----------------------------


@pytest.mark.parametrize(
    "cls, raw, val",
    [
        (AzureTextStore, b"hello", "hello"),
        (AzureJsonStore, b'{"a": 1}', {"a": 1}),
        (AzurePickleStore, __import__("pickle").dumps([1, 2]), [1, 2]),
    ],
)
def test_typed_store_trailing_slash_substore(cls, raw, val):
    cc = mk_container(blobs={"logs/2026/a": raw})
    s = cls(cc, prefix="logs/")
    sub = s["2026/"]
    assert isinstance(sub, cls)  # same typed class, not the bare leaf
    assert sub.prefix == "logs/2026/"
    assert sub["a"] == val  # still decoded
    assert s["2026/a"] == val


# ---- 2. delete_container ----------------------------------------------------------


def mk_account(containers):
    """An AccountStore over a fake service client; ``containers`` = {name: {blob: bytes}}."""
    acct = AccountStore.__new__(AccountStore)
    svc = MagicMock()
    ccs = {n: mk_container(n, b) for n, b in containers.items()}

    def get_cc(n):
        if n not in ccs:
            cc = mk_container(n)
            cc.exists.return_value = False
            return cc
        return ccs[n]

    svc.get_container_client.side_effect = get_cc
    svc.list_containers.side_effect = lambda: [FakeBlob(n) for n in ccs]
    for n, cc in ccs.items():
        cc.delete_container.side_effect = lambda n=n: ccs.pop(n)
    acct._service_client = svc
    acct._container_store_cls, acct._container_store_kwargs = ContainerStore, {}
    return acct, ccs


def tenant_view(acct):
    return Pipe(filt_iter.prefixes("tenantA-"), KeyCodecs.prefixed("tenantA-"))(acct)


def test_old_delete_method_is_gone_and_names_replacement():
    acct, _ = mk_account({})
    with pytest.raises(AttributeError, match="delete_container"):
        acct.delete("x", force=True)


def test_delete_container_maps_key_under_codec():
    acct, ccs = mk_account(
        {"tenantA-logs": {"keep": b"A"}, "logs": {"PRODUCTION.db": b"!"}}
    )
    view = tenant_view(acct)
    assert sorted(view) == ["logs"]
    delete_container(view, "logs", force=True)
    assert set(ccs) == {"logs"} and ccs["logs"].blobs == {"PRODUCTION.db": b"!"}


def test_delete_container_without_force_refuses_non_empty():
    acct, ccs = mk_account({"tenantA-logs": {"keep": b"A"}})
    with pytest.raises(ContainerNotEmptyError):
        delete_container(tenant_view(acct), "logs")
    assert "tenantA-logs" in ccs


def test_delete_container_scope_and_missing():
    acct, ccs = mk_account({"other": {"x": b"1"}})
    with pytest.raises(ContainerNotFoundError):
        delete_container(tenant_view(acct), "other", force=True)  # maps to tenantA-other
    assert "other" in ccs


def test_delete_container_bare_store_and_cascade_does_not_leak():
    acct, ccs = mk_account({"a": {"x": b"1"}, "b": {"y": b"2"}})
    delete_container(acct, "a", force=True)
    assert set(ccs) == {"b"}
    with pytest.raises(ContainerNotEmptyError):  # authorisation did not outlive the call
        del acct["b"]


def test_delete_container_respects_readonly_wrapper():
    from dol import Store

    acct, ccs = mk_account({"a": {}})

    class RO(Store):
        def __delitem__(self, k):
            raise PermissionError("read-only")

    with pytest.raises(PermissionError):
        delete_container(RO(acct), "a")
    assert "a" in ccs


# ---- 3. walk ---------------------------------------------------------------------


def test_walk_scope_includes_key_codec_prefix():
    cc = mk_container()
    leaf = ContainerStore(cc, prefix="logs/")
    wrapped = KeyCodecs.prefixed("2026/")(leaf)
    assert list(walk_container(leaf)) == [("walk", "logs/", "/")]
    assert list(walk_container(wrapped)) == [("walk", "logs/2026/", "/")]
    assert list(leaf.walk_ids()) == [("walk", "logs/", "/")]
    with pytest.raises(AttributeError, match="azuredol.ops.walk"):
        leaf.walk()


def test_cascade_authorisation_is_per_account():
    acct, ccs = mk_account({"logs": {"x": b"1"}})
    other, other_ccs = mk_account({"logs": {"y": b"2"}})
    from dol import Store

    class Mirror(Store):
        def __delitem__(self, k):
            del self.store[k]
            del other[k]  # a second account, same name, same call

    with pytest.raises(ContainerNotEmptyError):
        delete_container(Mirror(acct), "logs", force=True)
    assert "logs" in other_ccs and other_ccs["logs"].blobs == {"y": b"2"}


def test_walk_refuses_non_prefix_codec():
    cc = mk_container()
    leaf = ContainerStore(cc, prefix="logs/")
    with pytest.raises(ValueError, match="prefix"):
        walk_container(KeyCodecs.suffixed(".json")(leaf))


def test_typed_codec_decorator_for_azure_store():
    import json

    from azuredol import typed_codec

    cls = typed_codec(json.loads, lambda o: json.dumps(o).encode())(ContainerStore)
    cc = mk_container(blobs={"p/d/a": b"[1]"})
    s = cls(cc, prefix="p/")
    assert s["d/"]["a"] == [1]


# ---- 4. wrapper layers that cannot be resolved are refused (i2mint/azuredol#7) -------


class _Opaque:
    """A hand-rolled wrapper that maps keys but has no ``_id_of_key``."""

    def __init__(self, store, prefix):
        self.store, self.prefix = store, prefix

    def __contains__(self, k):
        return self.prefix + k in self.store

    def __delitem__(self, k):
        del self.store[self.prefix + k]


def test_delete_container_refuses_layer_without_id_of_key():
    acct, ccs = mk_account({"tenantA-logs": {"keep": b"A"}, "logs": {"prod": b"!"}})
    with pytest.raises(TypeError, match="_id_of_key"):
        delete_container(_Opaque(acct, "tenantA-"), "logs", force=True)
    assert set(ccs) == {"tenantA-logs", "logs"}  # nothing was deleted


def test_walk_refuses_layer_without_id_of_key():
    leaf = ContainerStore(mk_container(), prefix="logs/")
    with pytest.raises(TypeError, match="_id_of_key"):
        walk_container(_Opaque(leaf, "2026/"))


class _Delegating(_Opaque):
    """Forwards unknown attributes to the inner store: its ``_id_of_key`` is the leaf's."""

    def __getattr__(self, name):
        return getattr(self.store, name)


def test_layers_that_only_delegate_id_of_key_are_refused():
    leaf = ContainerStore(mk_container(), prefix="logs/")
    with pytest.raises(TypeError, match="_id_of_key"):
        walk_container(_Delegating(leaf, "2026/"))
