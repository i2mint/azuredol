"""Access Azure Blob Storage through a Mapping interface.

``azuredol`` exposes Azure Blob Storage as ``dol``-style ``Mapping`` /
``MutableMapping`` interfaces.

Quick start::

    from azuredol import azure_store

    # Uses connection_string env var or Azurite (UseDevelopmentStorage=true)
    store = azure_store(
        'mycontainer',
        connection_string='UseDevelopmentStorage=true',
        create_container_if_missing=True,
    )

    store['k1'] = b'hello world'
    store['k1']               # → b'hello world'
    'k1' in store             # → True
    del store['k1']

See ``misc/docs/architecture.md`` for the layered design.
"""

from azuredol.connection import AzureConnection, resolve_credential
from azuredol.base import (
    AccountCollection,
    AccountReader,
    AccountStore,
    BlobHandle,
    ContainerCollection,
    ContainerReader,
    ContainerStore,
)
from azuredol.errors import (
    BlobAlreadyExistsError,
    BlobNotFoundError,
    ContainerAlreadyExistsError,
    ContainerNotEmptyError,
    ContainerNotFoundError,
    translate_azure_errors,
)
from azuredol.recipes import (
    AppendBlobStore,
    AzureJsonStore,
    AzurePickleStore,
    AzureTextStore,
    azure_store,
    typed_codec,
    typed_store,
)
from azuredol.ops import delete_container, walk as walk_container
from azuredol.functions import azure_func_service


__all__ = [
    # connection
    "AzureConnection",
    "resolve_credential",
    # base / metal layer
    "AccountCollection",
    "AccountReader",
    "AccountStore",
    "BlobHandle",
    "ContainerCollection",
    "ContainerReader",
    "ContainerStore",
    # errors
    "BlobAlreadyExistsError",
    "BlobNotFoundError",
    "ContainerAlreadyExistsError",
    "ContainerNotEmptyError",
    "ContainerNotFoundError",
    "translate_azure_errors",
    # recipes / convenience
    "AppendBlobStore",
    "AzureJsonStore",
    "AzurePickleStore",
    "AzureTextStore",
    "azure_store",
    "typed_store",
    "typed_codec",
    # key-aware free functions (work through dol wrappers)
    "delete_container",
    "walk_container",
    # functions
    "azure_func_service",
]
