"""Convenience wrappers and factories for azuredol.

Layer C of the architecture. Built only by composition over Layer B (``base.py``).
See ``misc/docs/architecture.md`` Layer C.
"""

from __future__ import annotations

from functools import partial
from typing import Any, Callable, Optional, Union

from azure.storage.blob import BlobType
from dol import wrap_kvs

from azuredol.base import ContainerStore
from azuredol.connection import AzureConnection


# ---------------------------------------------------------------------------
# Typed-value stores (codec wrappers)
# ---------------------------------------------------------------------------

# Note: do NOT use `bytes.decode` directly as `obj_of_data` — known dol issue (#9).
AzureTextStore = wrap_kvs(
    ContainerStore,
    obj_of_data=lambda b: b.decode(),
    data_of_obj=lambda s: s.encode(),
)
"""Text-typed values (str ↔ bytes via UTF-8)."""


def _json_codec():
    """Lazy json import so this module is import-light."""
    import json

    return wrap_kvs(
        ContainerStore,
        obj_of_data=lambda b: json.loads(b),
        data_of_obj=lambda obj: json.dumps(obj).encode(),
    )


def _pickle_codec():
    import pickle

    return wrap_kvs(
        ContainerStore,
        obj_of_data=lambda b: pickle.loads(b),
        data_of_obj=lambda obj: pickle.dumps(obj),
    )


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
            a partially-applied ``dol.wrap_kvs(...)``. When None (default), bytes pass
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
