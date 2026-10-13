# azuredol.recipes

Convenience wrappers and factories for azuredol.

Layer C of the architecture. Built only by composition over Layer B (`base.py`).
See `misc/docs/architecture.md` Layer C.

### Module Attributes

| [`AzureTextStore`](#azuredol.recipes.AzureTextStore)   | Text-typed values (str ↔ bytes via UTF-8).                            |
|-------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`AzureJsonStore`](#azuredol.recipes.AzureJsonStore)   | JSON-typed values (dict/list/scalar ↔ bytes via `json`).              |
| [`AzurePickleStore`](#azuredol.recipes.AzurePickleStore) | Pickle-typed values (Python objects ↔ bytes via `pickle`).            |
| [`AppendBlobStore`](#azuredol.recipes.AppendBlobStore)  | `ContainerStore` whose `__setitem__` creates append blobs by default. |

### Functions

| [`azure_store`](#azuredol.recipes.azure_store)(container, \*[, prefix, ...])   | Build a ready-to-use `ContainerStore` (or codec-wrapped variant) in one call.                   |
|----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| [`typed_codec`](#azuredol.recipes.typed_codec)(decode, encode)                 | `typed_store` as a class decorator: the shape `azure_store(value_codec=...)` takes.             |
| [`typed_store`](#azuredol.recipes.typed_store)(decode, encode, \*[, base])     | A `base` (default `ContainerStore`) class with values `decode(bytes)` / `encode(obj) -> bytes`. |

### azuredol.recipes.AppendBlobStore *= functools.partial(<class 'azuredol.base.ContainerStore'>, blob_type=<BlobType.APPENDBLOB: 'AppendBlob'>)*

`ContainerStore` whose `__setitem__` creates append blobs by default.

Recall the Mapping caveat: `store[k] = v` on an append blob still creates a new
blob (`overwrite=True`) — it does NOT append to an existing blob. For incremental
appends use `BlobHandle(container, blob).append(data)`.

### azuredol.recipes.AzureJsonStore

JSON-typed values (dict/list/scalar ↔ bytes via `json`).

### azuredol.recipes.AzurePickleStore

Pickle-typed values (Python objects ↔ bytes via `pickle`).

### azuredol.recipes.AzureTextStore

Text-typed values (str ↔ bytes via UTF-8).

### azuredol.recipes.azure_store(container, , prefix='', connection=None, credential=None, connection_string=None, account_url=None, account_key=None, create_container_if_missing=False, blob_type=BlobType.BLOCKBLOB, value_codec=None)

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

### azuredol.recipes.typed_codec(decode, encode)

`typed_store` as a class decorator: the shape `azure_store(value_codec=...)` takes.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)

```pycon
>>> import json
>>> codec = typed_codec(json.loads, lambda o: json.dumps(o).encode())
>>> callable(codec)
True
```

### azuredol.recipes.typed_store(decode, encode, \*, base=<class 'azuredol.base.ContainerStore'>)

A `base` (default `ContainerStore`) class with values `decode(bytes)` / `encode(obj) -> bytes`.

Unlike a bare `wrap_kvs(ContainerStore, obj_of_data=..., data_of_obj=...)`, the trailing-slash
sub-store convention keeps working: `store['2026/']` comes back as a sub-store of the
*same typed class*, instead of being fed to `decode` (i2mint/azuredol#4).
