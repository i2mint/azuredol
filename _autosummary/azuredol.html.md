# azuredol

Access Azure Blob Storage through a Mapping interface.

`azuredol` exposes Azure Blob Storage as `dol`-style `Mapping` /
`MutableMapping` interfaces.

Quick start:

```default
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
```

See `misc/docs/architecture.md` for the layered design.

### Functions

| [`resolve_credential`](#azuredol.resolve_credential)(\*[, credential, ...])         | Resolve a credential into a normalized form that can build a `BlobServiceClient`.               |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| [`translate_azure_errors`](#azuredol.translate_azure_errors)(\*[, key_arg, ...])        | Decorator: translate Azure SDK exceptions into `KeyError` subclasses.                           |
| [`azure_store`](#azuredol.azure_store)(container, \*[, prefix, ...])         | Build a ready-to-use `ContainerStore` (or codec-wrapped variant) in one call.                   |
| [`typed_store`](#azuredol.typed_store)(decode, encode, \*[, base])           | A `base` (default `ContainerStore`) class with values `decode(bytes)` / `encode(obj) -> bytes`. |
| [`typed_codec`](#azuredol.typed_codec)(decode, encode)                       | `typed_store` as a class decorator: the shape `azure_store(value_codec=...)` takes.             |
| [`delete_container`](#azuredol.delete_container)(store, name, \*[, force])        | Delete container `name` (a key of `store`); with `force=True` cascade-delete its blobs.         |
| [`walk_container`](#azuredol.walk_container)(store[, delimiter])                | Hierarchical walk (`BlobProperties` / `BlobPrefix` nodes) of `store`'s own scope.               |
| [`substore`](#azuredol.substore)(store, key)                              | The sub-store of `store` under `key` (a key ending in `'/'`), as the caller sees it.            |
| [`azure_func_service`](#azuredol.azure_func_service)(rootfolder[, extra_args, ...]) | Context manager to start an Azure Function host using `func start` in the specified folder.     |

### Classes

| [`AzureConnection`](#azuredol.AzureConnection)([credential, ...])                | Holds a resolved credential and a lazy `BlobServiceClient`.                             |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| [`AccountCollection`](#azuredol.AccountCollection)([connection, ...])              | Mapping over container names in an account (iter / contains / len).                     |
| [`AccountReader`](#azuredol.AccountReader)([connection, ...])                  | Adds `__getitem__` returning a `ContainerStore` (or configured subclass).               |
| [`AccountStore`](#azuredol.AccountStore)([connection, ...])                   | Read-write Mapping over containers in an account.                                       |
| [`BlobHandle`](#azuredol.BlobHandle)(container, blob, \*[, connection])     | Thin facade over one `BlobClient`.                                                      |
| [`ContainerCollection`](#azuredol.ContainerCollection)(container, \*[, prefix, ...]) | Iteration / membership / cardinality (`__len__` deliberately omitted) over a container. |
| [`ContainerReader`](#azuredol.ContainerReader)(container, \*[, prefix, ...])     | Adds `__getitem__` (returns bytes) over `ContainerCollection`.                          |
| [`ContainerStore`](#azuredol.ContainerStore)(container, \*[, prefix, ...])      | The primary read-write Mapping over an Azure container.                                 |
| [`AzureJsonStore`](#azuredol.AzureJsonStore)                                    |                                                                                         |
| [`AzurePickleStore`](#azuredol.AzurePickleStore)                                  |                                                                                         |
| [`AzureTextStore`](#azuredol.AzureTextStore)                                    |                                                                                         |

### Exceptions

| [`BlobAlreadyExistsError`](#azuredol.BlobAlreadyExistsError)      | Raised on strict-create write attempts when the blob already exists.   |
|------------------------------------------------------------------------------|------------------------------------------------------------------------|
| [`BlobNotFoundError`](#azuredol.BlobNotFoundError)           | Raised when a blob does not exist.                                     |
| [`ContainerAlreadyExistsError`](#azuredol.ContainerAlreadyExistsError) | Raised on strict-create attempts when the container already exists.    |
| [`ContainerNotEmptyError`](#azuredol.ContainerNotEmptyError)      | Raised on `del account_store[name]` when the container has blobs.      |
| [`ContainerNotFoundError`](#azuredol.ContainerNotFoundError)      | Raised when a container does not exist.                                |

### *class* azuredol.AccountCollection(connection=None, , container_store_cls=None, container_store_kwargs=None)

Bases: `_AccountStoreBase`, `KvReader`

Mapping over container names in an account (iter / contains / len).

### *class* azuredol.AccountReader(connection=None, , container_store_cls=None, container_store_kwargs=None)

Bases: [`AccountCollection`](azuredol.base.html.md#azuredol.base.AccountCollection)

Adds `__getitem__` returning a `ContainerStore` (or configured subclass).

### *class* azuredol.AccountStore(connection=None, , container_store_cls=None, container_store_kwargs=None)

Bases: [`AccountReader`](azuredol.base.html.md#azuredol.base.AccountReader), `KvPersister`

Read-write Mapping over containers in an account.

`__setitem__` creates a container; the value is ignored except when it’s a
Mapping (in which case it is treated as an initial bulk-load).

`__delitem__` refuses non-empty containers — call `azuredol.ops.delete_container(store, name, force=True)`
to acknowledge a cascading delete. See `misc/docs/design_decisions.md` §12.

### *class* azuredol.AzureConnection(credential=None, connection_string=None, account_url=None, account_key=None, client_kwargs=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Holds a resolved credential and a lazy `BlobServiceClient`.

This is the dependency-injection seam for the whole package. Tests construct one
pointing at Azurite without touching any store class.

* **Parameters:**
  * **credential** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – explicit credential object, key string, or SAS string.
  * **connection_string** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – full connection string (overrides `credential`).
  * **account_url** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – storage account URL (with or without credential).
  * **account_key** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – shared-key for the account.

All four args are optional; the credential cascade in
`resolve_credential` is consulted if none are provided.

#### blob_client(container, blob)

Cheap derivation of a `BlobClient` from the shared service client.

#### container_client(container)

Cheap derivation of a `ContainerClient` from the shared service client.

#### *classmethod* from_anything(source)

Convenience: build an `AzureConnection` from a thing-or-spec.

Accepts:

> - `AzureConnection` (returned as-is)
> - `BlobServiceClient` (wrapped without further resolution)
> - `str` (connection string)
> - `dict` (passed as kwargs)
> - `None` (defer to env / AAD)
* **Return type:**
  [`AzureConnection`](azuredol.connection.html.md#azuredol.connection.AzureConnection)

#### *property* service_client *: BlobServiceClient*

The lazily-constructed `BlobServiceClient`. Cached for the connection’s lifetime.

### azuredol.AzureJsonStore

alias of [`ContainerStore`](azuredol.base.html.md#azuredol.base.ContainerStore)

### azuredol.AzurePickleStore

alias of [`ContainerStore`](azuredol.base.html.md#azuredol.base.ContainerStore)

### azuredol.AzureTextStore

alias of [`ContainerStore`](azuredol.base.html.md#azuredol.base.ContainerStore)

### *exception* azuredol.BlobAlreadyExistsError

Bases: [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)

Raised on strict-create write attempts when the blob already exists.

`KeyError` subclass for symmetry with `BlobNotFoundError` — both signal a
key-vs-store mismatch.

### *class* azuredol.BlobHandle(container, blob, , connection=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Thin facade over one `BlobClient`. Not a Mapping.

Use when you need the full Azure-blob surface for a single blob: metadata,
properties, conditional writes, leases, copy, append, SAS URL generation,
streaming downloads.

* **Parameters:**
  * **container** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), `ContainerClient`]) – An existing `ContainerClient` or a container name string.
  * **blob** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The blob name (relative to the container root; full path including ‘/’).
  * **connection** (`Union`[[`AzureConnection`](azuredol.connection.html.md#azuredol.connection.AzureConnection), `BlobServiceClient`, [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict), [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – Ignored if `container` is a `ContainerClient`. Otherwise
    resolved via `AzureConnection.from_anything`.

#### acquire_lease(lease_duration=-1)

Acquire a lease (15-60s, or -1 for infinite). Returns a `BlobLeaseClient`.

#### append(data)

Append bytes to an append-blob (creating it if absent).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### copy_from(source_url, , requires_sync=None)

Server-side copy from a URL. Same-account = sync; cross-account = async (poll).

#### create(data, , overwrite=False, \*\*kwargs)

Strict-create variant of `write`; raises `BlobAlreadyExistsError` on conflict.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### download_stream(, chunk_size=None)

Return a streaming downloader. Iterate chunks via `.chunks()` or `.readinto(fp)`.

#### properties()

Return `BlobProperties` (size, last_modified, etag, content_settings, metadata, …).

#### read(, offset=None, length=None)

Download (possibly a range) and return bytes.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

#### url(, expires_in=None)

Return the blob URL.

If `expires_in` is set and the underlying credential is a shared-key, a SAS
URL with read permission is generated. Otherwise the plain blob URL is returned
(which is only useful for public containers or pre-shared SAS contexts).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### write(data, , blob_type=BlobType.BLOCKBLOB, overwrite=True, content_type=None, metadata=None, \*\*kwargs)

Upload data; default overwrite=True for `MutableMapping` symmetry.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### *exception* azuredol.BlobNotFoundError

Bases: [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)

Raised when a blob does not exist. `KeyError` subclass so `Mapping` consumers work.

### *exception* azuredol.ContainerAlreadyExistsError

Bases: [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)

Raised on strict-create attempts when the container already exists.

### *class* azuredol.ContainerCollection(container, , prefix='', connection=None, create_container_if_missing=False, blob_type=BlobType.BLOCKBLOB, upload_kwargs=None, download_kwargs=None)

Bases: `_ContainerStoreBase`, `KvReader`

Iteration / membership / cardinality (`__len__` deliberately omitted) over a container.

`__len__` is intentionally NOT implemented — see
`misc/docs/design_decisions.md` §2. Pagination cost is unbounded; users wanting
a count call `sum(1 for _ in store)`.

#### walk_ids(delimiter='/')

Hierarchical walk of the *leaf’s* prefix, yielding `BlobProperties` / `BlobPrefix` nodes.

Thin pass-through to `ContainerClient.walk_blobs`. The scope is the leaf’s own
`prefix` and each node’s `.name` is an absolute blob id (never a store key), so
under a `dol` key codec it disagrees with `__iter__`. For a scope that follows
the caller’s (possibly wrapped) store use `azuredol.ops.walk(store)`.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### *exception* azuredol.ContainerNotEmptyError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised on `del account_store[name]` when the container has blobs.

The user must call `azuredol.delete_container(account_store, name, force=True)` to acknowledge the
cascading delete. See `misc/docs/design_decisions.md` §12.

### *exception* azuredol.ContainerNotFoundError

Bases: [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)

Raised when a container does not exist.

### *class* azuredol.ContainerReader(container, , prefix='', connection=None, create_container_if_missing=False, blob_type=BlobType.BLOCKBLOB, upload_kwargs=None, download_kwargs=None)

Bases: [`ContainerCollection`](azuredol.base.html.md#azuredol.base.ContainerCollection)

Adds `__getitem__` (returns bytes) over `ContainerCollection`.

The trailing-slash sub-store convention lives here: `store['sub/']` returns a new
`ContainerReader` with extended prefix and zero round-trips.

### *class* azuredol.ContainerStore(container, , prefix='', connection=None, create_container_if_missing=False, blob_type=BlobType.BLOCKBLOB, upload_kwargs=None, download_kwargs=None)

Bases: [`ContainerReader`](azuredol.base.html.md#azuredol.base.ContainerReader), `KvPersister`

The primary read-write Mapping over an Azure container.

Doctest below requires Azurite (or live Azure). It is shown but not auto-run.

Example (requires Azurite):

```pycon
>>> from azuredol import ContainerStore
>>> s = ContainerStore(
...     'my-test-container',
...     connection='UseDevelopmentStorage=true',
...     create_container_if_missing=True,
... )
>>> s['k1'] = b'v1'
>>> s['k1']
b'v1'
>>> 'k1' in s
True
>>> del s['k1']
```

For unit tests without Azurite, prototype with `dol`’s in-memory pattern:
`wrap_kvs(dict(), ...)`.

### azuredol.azure_func_service(rootfolder, extra_args='', , verbose=True, wait_for_log=None, timeout=30, print_output=True)

Context manager to start an Azure Function host using `func start` in the specified folder.

* **Parameters:**
  * **rootfolder** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – The directory containing the Azure Function App.
  * **extra_args** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – Additional command-line arguments for the `func start` command.
  * **wait_for_log** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – A substring or regular expression pattern that indicates when the service is ready.
    If provided, the context manager waits until a matching log line is detected.
  * **timeout** ([*int*](https://docs.python.org/3/builtins/functions.html#int)) – Maximum time in seconds to wait for the ready log message.
  * **print_output** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool)) – If True, prints the process output to stdout.
* **Yields:**
  *subprocess.Popen* – The process object representing the running Azure Functions host.

Usage Example:
: with azure_func_service(‘/path/to/azure_func’, extra_args=”–verbose”, wait_for_log=r’Host started’) as proc:
  : # Place code here to test the HTTP service.
    …

### azuredol.azure_store(container, , prefix='', connection=None, credential=None, connection_string=None, account_url=None, account_key=None, create_container_if_missing=False, blob_type=BlobType.BLOCKBLOB, value_codec=None)

Build a ready-to-use `ContainerStore` (or codec-wrapped variant) in one call.

This is the “simple things simple” entry point. For complex configurations construct
`AzureConnection` and `ContainerStore` directly.

* **Parameters:**
  * **container** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Container name.
  * **prefix** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Blob-name prefix to scope all keys.
  * **connection** (`Union`[[`AzureConnection`](azuredol.connection.html.md#azuredol.connection.AzureConnection), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict), [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – An `AzureConnection` (or anything `AzureConnection.from_anything`
    accepts) to reuse a service client. Mutually exclusive with the explicit
    `credential` / `connection_string` / `account_*` kwargs.
  * **credential** ([`Any`](https://docs.python.org/3/library/typing.html#typing.Any)) – Forwarded to
    `AzureConnection` when `connection` is None.
  * **connection_string** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Forwarded to
    `AzureConnection` when `connection` is None.
  * **account_url** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Forwarded to
    `AzureConnection` when `connection` is None.
  * **account_key** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Forwarded to
    `AzureConnection` when `connection` is None.
  * **create_container_if_missing** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Create the container on first use if absent.
  * **blob_type** (`BlobType`) – Default blob type for writes.
  * **value_codec** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)]) – A decorator that, given a class, returns a wrapped class. Typically
    `typed_codec(decode, encode)`. A bare `dol.wrap_kvs(...)` breaks the
    trailing-slash sub-store (i2mint/azuredol#4). When None (default), bytes pass
    through.
* **Returns:**
  A `ContainerStore` instance, possibly codec-wrapped.

### azuredol.delete_container(store, name, , force=False)

Delete container `name` (a key of `store`); with `force=True` cascade-delete its blobs.

The deletion is `del store[name]` on the caller’s own store, so a key codec maps
`name`, a read-only wrapper refuses, and a scoped view cannot reach out of scope.

* **Raises:**
  * [**ContainerNotFoundError**](#azuredol.ContainerNotFoundError) – if `name` is not a container of `store`
  * [**ContainerNotEmptyError**](#azuredol.ContainerNotEmptyError) – if the container has blobs and `force` is false
* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### azuredol.resolve_credential(, credential=None, connection_string=None, account_url=None, account_key=None)

Resolve a credential into a normalized form that can build a `BlobServiceClient`.

Cascade (first hit wins):

1. Explicit `credential=`
2. Explicit `connection_string=`
3. Explicit `account_url=` + `account_key=` (or just `account_url=` + AAD)
4. Env var `AZURE_STORAGE_CONNECTION_STRING`
5. Env vars `AZURE_STORAGE_ACCOUNT_URL` + `AZURE_STORAGE_ACCOUNT_KEY`
6. Env var `AZURE_STORAGE_ACCOUNT_URL` alone + `DefaultAzureCredential`

* **Returns:**
  `{"conn_str": "..."}`                            # for from_connection_string
  `{"account_url": "...", "credential": <obj>}`    # for \_\_init_\_
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
* **Raises:**
  [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – if no source resolves.

### azuredol.substore(store, key)

The sub-store of `store` under `key` (a key ending in `'/'`), as the caller sees it.

`substore(store, 'a/')[k]` is `store['a/' + k]` for every wrapper stack on `store` (up to the key limits below).
On a bare `ContainerStore` it is the cheap, server-scoped `store['a/']` (listing only
`a/`’s blobs). On anything wrapped (a `dol` key/value codec or scope, including the
classes `typed_store`/`AzureJsonStore` build) it is a `KeyCodecs.prefixed(key)` view
*of that store*, so the caller’s key and value mappings still apply; that view lists the
wrapped store’s whole scope and keeps the keys under `key`. (`store['a/']` on a store
wrapped as an instance is minted by the innermost class and does not know about the
wrappers: i2mint/azuredol#6.)

> The cheap path needs a leaf that does not override `_id_of_key` (a subclass that maps keys

gets the view). Attribute lookups on the view fall through to the wrapped store, so
`.prefix` and `.walk_ids()` of a view describe the parent’s scope: use
`walk()` on it. Needs `dol>=0.3.75` (its prefix view skips out-of-scope keys when
iterating).

* **Parameters:**
  * **store** – a `ContainerReader`/`ContainerStore`, wrapped or not
  * **key** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – a key ending in `'/'`, without a leading `'/'` or an inner `'//'`

### azuredol.translate_azure_errors(\*, key_arg=0, not_found_cls=<class 'azuredol.errors.BlobNotFoundError'>, exists_cls=<class 'azuredol.errors.BlobAlreadyExistsError'>)

Decorator: translate Azure SDK exceptions into `KeyError` subclasses.

Auth errors (`ClientAuthenticationError`) and all other Azure errors propagate
untouched — they are *never* swallowed as “key absent”. See
`misc/docs/design_decisions.md` §4.

* **Parameters:**
  * **key_arg** ([`int`](https://docs.python.org/3/builtins/functions.html#int) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Position (int) or name (str) of the key argument in the wrapped
    method’s signature. Used to populate `KeyError(key)`. The receiver
    `self` is at index 0, so the user-facing key is typically at index 1
    (the default).
  * **not_found_cls** ([`type`](https://docs.python.org/3/builtins/functions.html#type)[[`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)]) – Exception class to raise on `ResourceNotFoundError`.
  * **exists_cls** ([`type`](https://docs.python.org/3/builtins/functions.html#type)[[`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)]) – Exception class to raise on `ResourceExistsError`.
* **Return type:**
  [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)

### azuredol.typed_codec(decode, encode)

`typed_store` as a class decorator: the shape `azure_store(value_codec=...)` takes.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)

```pycon
>>> import json
>>> codec = typed_codec(json.loads, lambda o: json.dumps(o).encode())
>>> callable(codec)
True
```

### azuredol.typed_store(decode, encode, \*, base=<class 'azuredol.base.ContainerStore'>)

A `base` (default `ContainerStore`) class with values `decode(bytes)` / `encode(obj) -> bytes`.

Unlike a bare `wrap_kvs(ContainerStore, obj_of_data=..., data_of_obj=...)`, the trailing-slash
sub-store convention keeps working: `store['2026/']` comes back as a sub-store of the
*same typed class*, instead of being fed to `decode` (i2mint/azuredol#4).

### azuredol.walk_container(store, delimiter='/')

Hierarchical walk (`BlobProperties` / `BlobPrefix` nodes) of `store`’s own scope.

The scope is the blob prefix the caller’s empty key resolves to, so a key codec’s prefix
is included (a codec that is not a pure prefix, e.g. a suffix, raises `ValueError`; unlike `ContainerCollection.walk_ids`, which sees only the leaf’s prefix).

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### Modules

| [`base`](azuredol.base.html.md#module-azuredol.base)             | Close-to-metal Mapping stores over Azure Blob Storage.                                              |
|----------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| [`connection`](azuredol.connection.html.md#module-azuredol.connection) | Connection-layer for azuredol.                                                                      |
| [`errors`](azuredol.errors.html.md#module-azuredol.errors)         | Custom exceptions and error-translation decorator for azuredol.                                     |
| [`functions`](azuredol.functions.html.md#module-azuredol.functions)   | Azure functions tools                                                                               |
| [`ops`](azuredol.ops.html.md#module-azuredol.ops)               | Key-taking and scope-wide operations, as free functions over the caller's (possibly wrapped) store. |
| [`recipes`](azuredol.recipes.html.md#module-azuredol.recipes)       | Convenience wrappers and factories for azuredol.                                                    |
| [`testing`](azuredol.testing.html.md#module-azuredol.testing)       | Testing helpers for azuredol — Azurite fixture and convenience builders.                            |
