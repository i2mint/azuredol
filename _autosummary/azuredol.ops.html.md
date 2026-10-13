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

### azuredol.ops.walk(store, delimiter='/')

Hierarchical walk (`BlobProperties` / `BlobPrefix` nodes) of `store`’s own scope.

The scope is the blob prefix the caller’s empty key resolves to, so a key codec’s prefix
is included (a codec that is not a pure prefix, e.g. a suffix, raises `ValueError`; unlike `ContainerCollection.walk_ids`, which sees only the leaf’s prefix).

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]
