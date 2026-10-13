"""Convenience wrappers and factories for azuredol.

Layer C of the architecture. Built only by composition over Layer B (``base.py``).
See ``misc/docs/architecture.md`` Layer C.
"""

from __future__ import annotations

from functools import partial
from typing import Any, Callable, Optional, Union

from azure.storage.blob import BlobType
from dol import wrap_kvs

from azuredol.base import ContainerReader, ContainerStore
from azuredol.connection import AzureConnection


# ---------------------------------------------------------------------------
# Typed-value stores (codec wrappers)
# ---------------------------------------------------------------------------

def typed_store(decode: Callable, encode: Callable, *, base: type = ContainerStore):
    """A ``base`` (default ``ContainerStore``) class with values ``decode(bytes)`` / ``encode(obj) -> bytes``.

    Unlike a bare ``wrap_kvs(ContainerStore, obj_of_data=..., data_of_obj=...)``, the trailing-slash
    sub-store convention keeps working: ``store['2026/']`` comes back as a sub-store of the
    *same typed class*, instead of being fed to ``decode`` (i2mint/azuredol#4).
    """

    def obj_of_data(x):
        if isinstance(x, ContainerReader):  # a trailing-slash sub-store, not blob bytes
            return cls(**x._init_kwargs())
        return decode(x)

    cls = wrap_kvs(base, obj_of_data=obj_of_data, data_of_obj=encode)
    return cls


def typed_codec(decode: Callable, encode: Callable) -> Callable:
    """``typed_store`` as a class decorator: the shape ``azure_store(value_codec=...)`` takes.

    >>> import json
    >>> codec = typed_codec(json.loads, lambda o: json.dumps(o).encode())
    >>> callable(codec)
    True
    """
    return lambda base: typed_store(decode, encode, base=base)


# Note: do NOT use `bytes.decode` directly as `obj_of_data` — known dol issue (#9).
AzureTextStore = typed_store(lambda b: b.decode(), lambda s: s.encode())
"""Text-typed values (str ↔ bytes via UTF-8)."""


def _json_codec():
    """Lazy json import so this module is import-light."""
    import json

    return typed_store(lambda b: json.loads(b), lambda obj: json.dumps(obj).encode())


def _pickle_codec():
    import pickle

    return typed_store(lambda b: pickle.loads(b), lambda obj: pickle.dumps(obj))


# Built lazily so importing azuredol.recipes doesn't import json/pickle eagerly.
AzureJsonStore = _json_codec()
"""JSON-typed values (dict/list/scalar ↔ bytes via ``json``)."""

AzurePickleStore = _pickle_codec()
"""Pickle-typed values (Python objects ↔ bytes via ``pickle``)."""


# ---------------------------------------------------------------------------
# Append-blob variant (named alias)
# ---------------------------------------------------------------------------

AppendBlobStore = partial(ContainerStore, blob_type=BlobType.AppendBlob)
"""``ContainerStore`` whose ``__setitem__`` creates append blobs by default.

Recall the Mapping caveat: ``store[k] = v`` on an append blob still creates a new
blob (``overwrite=True``) — it does NOT append to an existing blob. For incremental
appends use ``BlobHandle(container, blob).append(data)``.
"""


# ---------------------------------------------------------------------------
# One-call factory
# ---------------------------------------------------------------------------


def azure_store(
    container: str,
    *,
    prefix: str = "",
    connection: Union[AzureConnection, str, dict, None] = None,
    credential: Any = None,
    connection_string: Optional[str] = None,
    account_url: Optional[str] = None,
    account_key: Optional[str] = None,
    create_container_if_missing: bool = False,
    blob_type: BlobType = BlobType.BlockBlob,
    value_codec: Optional[Callable] = None,
):
    """Build a ready-to-use ``ContainerStore`` (or codec-wrapped variant) in one call.

    This is the "simple things simple" entry point. For complex configurations construct
    ``AzureConnection`` and ``ContainerStore`` directly.

    Args:
        container: Container name.
        prefix: Blob-name prefix to scope all keys.
        connection: An ``AzureConnection`` (or anything ``AzureConnection.from_anything``
            accepts) to reuse a service client. Mutually exclusive with the explicit
            ``credential`` / ``connection_string`` / ``account_*`` kwargs.
        credential, connection_string, account_url, account_key: Forwarded to
            ``AzureConnection`` when ``connection`` is None.
        create_container_if_missing: Create the container on first use if absent.
        blob_type: Default blob type for writes.
        value_codec: A decorator that, given a class, returns a wrapped class. Typically
            ``typed_codec(decode, encode)``. A bare ``dol.wrap_kvs(...)`` breaks the
            trailing-slash sub-store (i2mint/azuredol#4). When None (default), bytes pass
            through.

    Returns:
        A ``ContainerStore`` instance, possibly codec-wrapped.
    """
    if connection is not None and (
        credential is not None
        or connection_string is not None
        or account_url is not None
        or account_key is not None
    ):
        raise ValueError(
            "Pass either `connection=...` or the explicit "
            "(credential|connection_string|account_url|account_key) kwargs — not both."
        )

    conn = (
        AzureConnection.from_anything(connection)
        if connection is not None
        else AzureConnection(
            credential=credential,
            connection_string=connection_string,
            account_url=account_url,
            account_key=account_key,
        )
    )

    cls = ContainerStore
    if value_codec is not None:
        cls = value_codec(cls)

    return cls(
        container,
        prefix=prefix,
        connection=conn,
        create_container_if_missing=create_container_if_missing,
        blob_type=blob_type,
    )
