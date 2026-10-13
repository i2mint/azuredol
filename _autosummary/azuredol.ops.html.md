# azuredol.ops

Key-taking and scope-wide operations, as free functions over the caller’s (possibly wrapped) store.

`dol` wraps stores by delegation, so a *method* of a wrapped azuredol store runs bound to
the inner leaf: it receives the caller’s **outer**, unmapped key and reads the leaf’s own
`prefix` (i2mint/azuredol#4, i2mint/dol#83). Under a key codec that made
`AccountStore.delete('logs', force=True)` cascade-delete the container literally named
`logs` instead of `tenantA-logs`, and `ContainerCollection.walk` list the wrong scope.
A free function is handed the outer store, so it resolves the key through every layer:

- [`delete_container()`](#azuredol.ops.delete_container) `(store, name, force=False)`: `del store[name]` through the
  caller’s store, with a context-scoped authorisation to cascade for that one container.
  Key mapping, read-only wrappers and scope checks (`name in store`) are the layers’ own.
- [`walk()`](#azuredol.ops.walk) `(store, delimiter)`: `walk_blobs` over the prefix the *caller’s* empty
  key resolves to (leaf prefix + any key codec).
- [`substore()`](#azuredol.ops.substore) `(store, key)`: the sub-store `store['2026/']` is meant to be, built
  through the caller’s own store (i2mint/azuredol#6): `substore(store, 'a/')[k]` is always
  `store['a/' + k]`, whatever wrappers (key or value codecs, scopes) sit on `store`.

The removed methods (`AccountStore.delete`, `ContainerCollection.walk`) now raise an
`AttributeError` naming their replacement. This is the design of cosmodol.ops and s3dol’s
ADR-0011.

What stays outside reach, stated rather than hidden: [`walk()`](#azuredol.ops.walk) yields raw Azure nodes whose
`.name` is an absolute blob id (azure’s own objects), and a `filt_iter` scope that filters
by key cannot narrow a server-side walk. A layer that performs the delete in another thread
escapes the cascade authorisation (the delete is then refused as non-empty, never widened).

### Functions

| [`delete_container`](#azuredol.ops.delete_container)(store, name, \*[, force])   | Delete container `name` (a key of `store`); with `force=True` cascade-delete its blobs.   |
|-----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| [`substore`](#azuredol.ops.substore)(store, key)                         | The sub-store of `store` under `key` (a key ending in `'/'`), as the caller sees it.      |
| [`walk`](#azuredol.ops.walk)(store[, delimiter])                     | Hierarchical walk (`BlobProperties` / `BlobPrefix` nodes) of `store`'s own scope.         |

### azuredol.ops.delete_container(store, name, , force=False)

Delete container `name` (a key of `store`); with `force=True` cascade-delete its blobs.

The deletion is `del store[name]` on the caller’s own store, so a key codec maps
`name`, a read-only wrapper refuses, and a scoped view cannot reach out of scope.

* **Raises:**
  * [**ContainerNotFoundError**](azuredol.html.md#azuredol.ContainerNotFoundError) – if `name` is not a container of `store`
  * [**ContainerNotEmptyError**](azuredol.html.md#azuredol.ContainerNotEmptyError) – if the container has blobs and `force` is false
* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### azuredol.ops.substore(store, key)

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
[`walk()`](#azuredol.ops.walk) on it. Needs `dol>=0.3.75` (its prefix view skips out-of-scope keys when
iterating).

* **Parameters:**
  * **store** – a `ContainerReader`/`ContainerStore`, wrapped or not
  * **key** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – a key ending in `'/'`, without a leading `'/'` or an inner `'//'`

### azuredol.ops.walk(store, delimiter='/')

Hierarchical walk (`BlobProperties` / `BlobPrefix` nodes) of `store`’s own scope.

The scope is the blob prefix the caller’s empty key resolves to, so a key codec’s prefix
is included (a codec that is not a pure prefix, e.g. a suffix, raises `ValueError`; unlike `ContainerCollection.walk_ids`, which sees only the leaf’s prefix).

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]
