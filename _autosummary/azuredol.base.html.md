# azuredol.base

Close-to-metal Mapping stores over Azure Blob Storage.

Three concrete classes:

- `ContainerStore` — the primary store. Mapping of blob name → bytes within one container.
- `AccountStore` — mapping of container name → `ContainerStore` within one account.
- `BlobHandle`  — non-Mapping escape hatch for one blob with the full Azure surface.

See `misc/docs/architecture.md` Layer B. Codec / convenience layers live in
`azuredol.recipes`; the connection layer lives in `azuredol.connection`.

### Classes

| [`AccountCollection`](#azuredol.base.AccountCollection)([connection, ...])              | Mapping over container names in an account (iter / contains / len).                     |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| [`AccountReader`](#azuredol.base.AccountReader)([connection, ...])                  | Adds `__getitem__` returning a `ContainerStore` (or configured subclass).               |
| [`AccountStore`](#azuredol.base.AccountStore)([connection, ...])                   | Read-write Mapping over containers in an account.                                       |
| [`BlobHandle`](#azuredol.base.BlobHandle)(container, blob, \*[, connection])     | Thin facade over one `BlobClient`.                                                      |
| [`ContainerCollection`](#azuredol.base.ContainerCollection)(container, \*[, prefix, ...]) | Iteration / membership / cardinality (`__len__` deliberately omitted) over a container. |
| [`ContainerReader`](#azuredol.base.ContainerReader)(container, \*[, prefix, ...])     | Adds `__getitem__` (returns bytes) over `ContainerCollection`.                          |
| [`ContainerStore`](#azuredol.base.ContainerStore)(container, \*[, prefix, ...])      | The primary read-write Mapping over an Azure container.                                 |

### *class* azuredol.base.AccountCollection(connection=None, , container_store_cls=None, container_store_kwargs=None)

Bases: `_AccountStoreBase`, `KvReader`

Mapping over container names in an account (iter / contains / len).

### *class* azuredol.base.AccountReader(connection=None, , container_store_cls=None, container_store_kwargs=None)

Bases: [`AccountCollection`](#azuredol.base.AccountCollection)

Adds `__getitem__` returning a `ContainerStore` (or configured subclass).

### *class* azuredol.base.AccountStore(connection=None, , container_store_cls=None, container_store_kwargs=None)

Bases: [`AccountReader`](#azuredol.base.AccountReader), `KvPersister`

Read-write Mapping over containers in an account.

`__setitem__` creates a container; the value is ignored except when it’s a
Mapping (in which case it is treated as an initial bulk-load).

`__delitem__` refuses non-empty containers — call `azuredol.ops.delete_container(store, name, force=True)`
to acknowledge a cascading delete. See `misc/docs/design_decisions.md` §12.

### *class* azuredol.base.BlobHandle(container, blob, , connection=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Thin facade over one `BlobClient`. Not a Mapping.

Use when you need the full Azure-blob surface for a single blob: metadata,
properties, conditional writes, leases, copy, append, SAS URL generation,
streaming downloads.

* **Parameters:**
  * **container** ([`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), `ContainerClient`]) – An existing `ContainerClient` or a container name string.
  * **blob** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The blob name (relative to the container root; full path including ‘/’).
  * **connection** ([`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`AzureConnection`](azuredol.connection.html.md#azuredol.connection.AzureConnection), `BlobServiceClient`, [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict), [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – Ignored if `container` is a `ContainerClient`. Otherwise
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

### *class* azuredol.base.ContainerCollection(container, , prefix='', connection=None, create_container_if_missing=False, blob_type=BlobType.BLOCKBLOB, upload_kwargs=None, download_kwargs=None)

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

### *class* azuredol.base.ContainerReader(container, , prefix='', connection=None, create_container_if_missing=False, blob_type=BlobType.BLOCKBLOB, upload_kwargs=None, download_kwargs=None)

Bases: [`ContainerCollection`](#azuredol.base.ContainerCollection)

Adds `__getitem__` (returns bytes) over `ContainerCollection`.

The trailing-slash sub-store convention lives here: `store['sub/']` returns a new
`ContainerReader` with extended prefix and zero round-trips. This works on a bare store
and on typed-store classes, but not through every wrapper stack (a `dol` wrapper placed
on an instance is not carried into the sub-store); [`azuredol.substore()`](azuredol.html.md#azuredol.substore) is the portable
form and should be preferred (i2mint/azuredol#9).

### *class* azuredol.base.ContainerStore(container, , prefix='', connection=None, create_container_if_missing=False, blob_type=BlobType.BLOCKBLOB, upload_kwargs=None, download_kwargs=None)

Bases: [`ContainerReader`](#azuredol.base.ContainerReader), `KvPersister`

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
