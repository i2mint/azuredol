"""Integration tests for azuredol against Azurite.

Requires Docker (or an already-running Azurite). Tests are skipped cleanly when
neither is available. See ``azuredol.testing.azurite`` for the fixture.

Run with::

    pytest azuredol/tests/test_integration_azurite.py -v -m integration

Or skip them in unit-test runs by adding ``-m "not integration"``.
"""

import json
import uuid

import pytest

from azuredol import (
    AccountStore,
    AppendBlobStore,
    AzureConnection,
    AzureJsonStore,
    AzureTextStore,
    BlobHandle,
    BlobNotFoundError,
    ContainerStore,
    azure_store,
)
from azuredol.testing import (
    AZURITE_CONNECTION_STRING,
    azurite_is_running,
    docker_available,
)


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def azurite_connection_string():
    """Yield an Azurite connection string; start Azurite via Docker if needed.

    Skips the integration tests entirely if neither is available.
    """
    if azurite_is_running():
        yield AZURITE_CONNECTION_STRING
        return
    if not docker_available():
        pytest.skip(
            "Azurite is not running and Docker is unavailable. "
            "Start Azurite manually: "
            "`docker run -p 10000:10000 mcr.microsoft.com/azure-storage/azurite`",
            allow_module_level=False,
        )
    # docker_available + not running: start it via the context manager.
    from azuredol.testing import azurite as _azurite_cm

    with _azurite_cm() as cs:
        yield cs


@pytest.fixture(scope="session")
def azure_connection(azurite_connection_string):
    return AzureConnection(connection_string=azurite_connection_string)


@pytest.fixture
def container_name():
    """A fresh container name per test, automatically cleaned up at session end."""
    return f"azdtest-{uuid.uuid4().hex[:10]}"


@pytest.fixture
def container_store(azure_connection, container_name):
    """A ContainerStore backed by a fresh Azurite container; cleaned up after the test."""
    store = ContainerStore(
        container_name,
        connection=azure_connection,
        create_container_if_missing=True,
    )
    try:
        yield store
    finally:
        # Best-effort cleanup: delete all blobs and the container.
        cc = store._container_client
        try:
            for blob in cc.list_blobs():
                cc.delete_blob(blob.name)
            cc.delete_container()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ContainerStore — full lifecycle
# ---------------------------------------------------------------------------


def test_set_get_round_trip_bytes(container_store):
    container_store["k1"] = b"hello"
    assert container_store["k1"] == b"hello"


def test_set_get_round_trip_str(container_store):
    container_store["k1"] = "hello as str"
    assert container_store["k1"] == b"hello as str"


def test_contains(container_store):
    container_store["k1"] = b"v1"
    assert "k1" in container_store
    assert "k99" not in container_store


def test_iter(container_store):
    container_store["a"] = b"1"
    container_store["b"] = b"2"
    container_store["c"] = b"3"
    assert set(container_store) == {"a", "b", "c"}


def test_delete(container_store):
    container_store["k1"] = b"v1"
    del container_store["k1"]
    assert "k1" not in container_store


def test_missing_raises_blobnotfound(container_store):
    with pytest.raises(KeyError) as ei:
        container_store["nope"]
    assert isinstance(ei.value, BlobNotFoundError)


def test_delete_missing_raises_blobnotfound(container_store):
    with pytest.raises(KeyError) as ei:
        del container_store["nope"]
    assert isinstance(ei.value, BlobNotFoundError)


def test_overwrite_default(container_store):
    """__setitem__ overwrites by default (Mapping contract)."""
    container_store["k1"] = b"v1"
    container_store["k1"] = b"v2"
    assert container_store["k1"] == b"v2"


def test_len_not_implemented(container_store):
    """ContainerStore deliberately does not implement __len__ (unbounded cost)."""
    with pytest.raises(TypeError):
        len(container_store)


# ---------------------------------------------------------------------------
# Prefix sub-stores
# ---------------------------------------------------------------------------


def test_prefix_scopes_iteration(azure_connection, container_name):
    full = ContainerStore(
        container_name, connection=azure_connection, create_container_if_missing=True
    )
    try:
        full["other/x"] = b"other"
        full["logs/a"] = b"1"
        full["logs/b"] = b"2"
        scoped = ContainerStore(
            container_name, prefix="logs/", connection=azure_connection
        )
        assert set(scoped) == {"a", "b"}
        assert scoped["a"] == b"1"
    finally:
        cc = full._container_client
        for b in cc.list_blobs():
            cc.delete_blob(b.name)
        cc.delete_container()


def test_trailing_slash_returns_substore(container_store):
    container_store["sub/x"] = b"1"
    container_store["sub/y"] = b"2"
    container_store["other"] = b"3"
    sub = container_store["sub/"]
    assert isinstance(sub, ContainerStore)
    assert set(sub) == {"x", "y"}
    assert sub["x"] == b"1"


# ---------------------------------------------------------------------------
# Codec recipes
# ---------------------------------------------------------------------------


def test_azure_json_store(azure_connection, container_name):
    store = AzureJsonStore(
        container_name, connection=azure_connection, create_container_if_missing=True
    )
    try:
        store["doc"] = {"name": "Alice", "age": 30}
        assert store["doc"] == {"name": "Alice", "age": 30}
        # Underlying bytes really are JSON.
        raw = ContainerStore(container_name, connection=azure_connection)["doc"]
        assert json.loads(raw) == {"name": "Alice", "age": 30}
    finally:
        cc = store._container_client
        for b in cc.list_blobs():
            cc.delete_blob(b.name)
        cc.delete_container()


def test_azure_text_store(azure_connection, container_name):
    store = AzureTextStore(
        container_name, connection=azure_connection, create_container_if_missing=True
    )
    try:
        store["greeting"] = "hello world"
        assert store["greeting"] == "hello world"
    finally:
        cc = store._container_client
        for b in cc.list_blobs():
            cc.delete_blob(b.name)
        cc.delete_container()


# ---------------------------------------------------------------------------
# BlobHandle — single-blob escape hatch
# ---------------------------------------------------------------------------


def test_blob_handle_lifecycle(azure_connection, container_name):
    # Use a ContainerStore just to create the container.
    cs = ContainerStore(
        container_name, connection=azure_connection, create_container_if_missing=True
    )
    try:
        h = BlobHandle(container_name, "single.bin", connection=azure_connection)
        assert not h.exists()
        h.write(b"hello")
        assert h.exists()
        assert h.read() == b"hello"
        props = h.properties()
        assert props.size == 5
        h.delete()
        assert not h.exists()
    finally:
        cc = cs._container_client
        for b in cc.list_blobs():
            cc.delete_blob(b.name)
        cc.delete_container()


def test_blob_handle_range_read(azure_connection, container_name):
    cs = ContainerStore(
        container_name, connection=azure_connection, create_container_if_missing=True
    )
    try:
        h = BlobHandle(container_name, "ranged.bin", connection=azure_connection)
        h.write(b"the quick brown fox")
        assert h.read(offset=4, length=5) == b"quick"
    finally:
        cc = cs._container_client
        for b in cc.list_blobs():
            cc.delete_blob(b.name)
        cc.delete_container()


def test_blob_handle_append(azure_connection, container_name):
    cs = ContainerStore(
        container_name, connection=azure_connection, create_container_if_missing=True
    )
    try:
        h = BlobHandle(container_name, "log.txt", connection=azure_connection)
        h.append(b"line 1\n")
        h.append(b"line 2\n")
        assert h.read() == b"line 1\nline 2\n"
    finally:
        cc = cs._container_client
        for b in cc.list_blobs():
            cc.delete_blob(b.name)
        cc.delete_container()


# ---------------------------------------------------------------------------
# AccountStore — container-level ops
# ---------------------------------------------------------------------------


def test_account_iter_contains(azure_connection, container_name):
    cs = ContainerStore(
        container_name, connection=azure_connection, create_container_if_missing=True
    )
    try:
        acct = AccountStore(azure_connection)
        assert container_name in acct
        assert container_name in set(acct)
    finally:
        cc = cs._container_client
        cc.delete_container()


def test_account_delete_refuses_nonempty(azure_connection, container_name):
    from azuredol import ContainerNotEmptyError

    cs = ContainerStore(
        container_name, connection=azure_connection, create_container_if_missing=True
    )
    cs["k1"] = b"v1"
    try:
        acct = AccountStore(azure_connection)
        with pytest.raises(ContainerNotEmptyError):
            del acct[container_name]
        # Force-delete works.
        acct.delete(container_name, force=True)
        assert container_name not in acct
    finally:
        # If the test failed before .delete, clean up.
        try:
            cs._container_client.delete_container()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Top-level factory
# ---------------------------------------------------------------------------


def test_azure_store_factory(azurite_connection_string, container_name):
    store = azure_store(
        container_name,
        connection_string=azurite_connection_string,
        create_container_if_missing=True,
    )
    try:
        store["k1"] = b"factory"
        assert store["k1"] == b"factory"
    finally:
        cc = store._container_client
        for b in cc.list_blobs():
            cc.delete_blob(b.name)
        cc.delete_container()
