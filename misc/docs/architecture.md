# azuredol — Architecture

`azuredol` exposes **Azure Blob Storage** as `dol`-style `Mapping` / `MutableMapping` interfaces.
This document is the single source of truth for the package's layering. It is intended to be
read by future contributors and by AI agents (see `azuredol/.claude/skills/azuredol/SKILL.md`,
which is generated from this doc).

For the underlying SDK / service reference, see [azure_blob_reference.md](azure_blob_reference.md).
For the *why* behind every defaulted choice, see [design_decisions.md](design_decisions.md).

---

## Goals

1. **Pythonic.** `store[key]`, `store[key] = value`, `del store[key]`, `key in store`, `for key in store:` — that is the surface. Everything else is opt-in.
2. **Faithful to the backend.** Errors come back as `KeyError` for the obvious "not found" case, but operations like soft delete, snapshots, versioning, leases, ETag conditions, and content-type metadata stay reachable through explicit methods.
3. **Composable with `dol`.** Once you have a close-to-metal store, you should be able to layer JSON / pickle / gzip / etc. codecs on top with one line (`wrap_kvs`, `Pipe`, `ValueCodecs`).
4. **Testable without a cloud.** Every test runs against [Azurite](https://learn.microsoft.com/en-us/azure/storage/common/storage-use-azurite) (Microsoft's emulator) — no live Azure account needed for development.
5. **Cheap in network round-trips.** No probe-then-act patterns; let the SDK raise and translate the error.

## The three layers

```
┌──────────────────────────────────────────────────────────────┐
│  Layer C — convenience wrappers (azuredol.recipes)           │
│  Codec layers, prefix sub-stores, factory helpers,           │
│  one-call `mk_azure_store(...)`                              │
├──────────────────────────────────────────────────────────────┤
│  Layer B — close-to-metal mapping stores (azuredol.base)     │
│  AccountStore, ContainerStore (the primary), BlobHandle      │
│  bytes in/out, KeyError translation, no codecs               │
├──────────────────────────────────────────────────────────────┤
│  Layer A — connection / context (azuredol.connection)        │
│  Credential resolution, BlobServiceClient caching, defaults  │
├──────────────────────────────────────────────────────────────┤
│       azure-storage-blob SDK (BlobServiceClient, …)          │
└──────────────────────────────────────────────────────────────┘
```

Every public class belongs to exactly one layer. No mixing.

### Layer A — Connection / context (`azuredol.connection`)

Owns the **expensive resource**: the `BlobServiceClient`. Holds:

- A resolved credential (one of: AAD `DefaultAzureCredential`, account key, SAS, connection string).
- A `BlobServiceClient` exposed via `cached_property` (lazy).
- Default options that propagate downwards: retry policy, `max_concurrency`, default `BlobType`, default `overwrite=True` for writes.

This is the **Dependency Injection seam**. Tests inject a connection pointed at Azurite without any store class knowing.

#### Credential resolution order

A single function `resolve_credential(...)` walks this cascade (first hit wins):

1. Explicit `credential=` kwarg.
2. Explicit `connection_string=` kwarg.
3. Env var `AZURE_STORAGE_CONNECTION_STRING`.
4. Env vars `AZURE_STORAGE_ACCOUNT_URL` + `AZURE_STORAGE_ACCOUNT_KEY`.
5. Env var `AZURE_STORAGE_ACCOUNT_URL` alone + `DefaultAzureCredential()`.
6. Raise an actionable error listing all five sources.

### Layer B — Close-to-metal stores (`azuredol.base`)

Three concrete classes, each wrapping the most specific SDK client and exposing the minimum
useful surface — no codecs, no convenience:

| Class | Backs | Keys | Values | Mapping? |
|---|---|---|---|---|
| `AccountStore` | `BlobServiceClient` | container names (`str`) | `ContainerStore` instances | yes (`KvPersister`) |
| `ContainerStore` | `ContainerClient` | blob names (`str`) | blob bytes | yes (`KvPersister`) — **the primary store** |
| `BlobHandle` | `BlobClient` | n/a | n/a | **no** — escape hatch for one blob with full API (`read`, `write`, `append`, `delete`, `exists`, `properties`, `copy_from`, `lease`, `url`) |

Subclasses for reader-only variants follow the `dol/filesys.py` triangle:

```
AccountCollection             (Collection — iter/contains/len of container names)
   └── AccountReader          (+ __getitem__  → ContainerStore for that container)
        └── AccountStore      (+ __setitem__/__delitem__ for containers)

ContainerCollection           (Collection — iter/contains/len of blob names)
   └── ContainerReader        (+ __getitem__  → bytes)
        └── ContainerStore    (+ __setitem__/__delitem__ for blobs)
```

#### Why no per-blob-type subclasses

`BlockBlobStore` / `AppendBlobStore` / `PageBlobStore` would create a 3×2 combinatorial
explosion across account/container scopes for negligible gain. The SDK already exposes them
as one `BlobClient` discriminated by methods. We expose them through:

- A `blob_type=BlobType.BlockBlob` kwarg on `ContainerStore` controlling `__setitem__`.
- `BlobHandle.append(...)` / `.upload_page(...)` for the per-call cases.
- A `recipes.AppendBlobStore = partial(ContainerStore, blob_type=BlobType.AppendBlob)` thin alias for the common opt-in.

### Layer C — Convenience (`azuredol.recipes`)

Built **only** by `wrap_kvs` / `Pipe` / `mk_relative_path_store` composition. Never by subclassing.

Standard recipes:

```python
from dol import wrap_kvs, ValueCodecs, KeyCodecs, Pipe, mk_relative_path_store

# JSON values
AzureJsonStore = wrap_kvs(ContainerStore, value_codec=ValueCodecs.json())

# Pickle values
AzurePickleStore = wrap_kvs(ContainerStore, value_codec=ValueCodecs.pickle())

# Filter by suffix
AzureJsonFiles = Pipe(KeyCodecs.suffixed(".json"), ValueCodecs.json())(ContainerStore)

# Text values (drop-in for the old AzureTextFiles)
AzureTextStore = wrap_kvs(
    ContainerStore, obj_of_data=lambda b: b.decode(), data_of_obj=lambda s: s.encode()
)

# Append-blob variant
AppendBlobStore = partial(ContainerStore, blob_type=BlobType.AppendBlob)
```

Plus one **top-level factory** for the simple things:

```python
azure_store(
    container: str,
    *,
    prefix: str = "",
    credential: ... = None,
    connection_string: str = None,
    create_container_if_missing: bool = False,
    blob_type: BlobType = BlobType.BlockBlob,
    value_codec: Codec = None,
) -> ContainerStore  # possibly wrapped
```

## Contracts the close-to-metal layer enforces

These are the only behaviors a Layer B store is *required* to deliver. Wrappers in Layer C
inherit them automatically.

| Operation | Contract |
|---|---|
| `__getitem__(k)` | Returns `bytes`. Raises `KeyError(k)` when blob is absent. Re-raises auth errors untouched. |
| `__setitem__(k, v)` | Accepts `bytes`, `str`, or any object with `.read()`. Overwrites by default. No error if blob is absent. |
| `__delitem__(k)` | Removes the blob (or, with soft delete on the account, marks it). Raises `KeyError(k)` only on missing-blob; everything else re-raised. |
| `__contains__(k)` | One network round-trip via `BlobClient.exists()`. Returns `False` on `ResourceNotFoundError`; re-raises auth errors. |
| `__iter__()` | Yields blob names (relative to `prefix`, if any), lazily, paginated. |
| `__len__()` | **Not implemented** — pagination cost is unbounded. Users who really want a count call `sum(1 for _ in store)` and own the cost. |
| `__repr__` | Includes container + prefix + blob type. |

A small `@translate_azure_errors(key_arg=...)` decorator does the `ResourceNotFoundError → KeyError` translation; it is the **only** place that catches Azure exceptions in the metal layer.

## Sub-stores and prefix scoping

`ContainerStore` carries a `prefix` and is wrapped at construction with
`mk_relative_path_store(prefix_attr='prefix')`. As a result:

```python
store = azure_store("mycontainer", prefix="logs/")
store["2026/05/22.log"]  # blob path = 'logs/2026/05/22.log'
sub = store["2026/"]  # → ContainerStore with prefix='logs/2026/'  (zero round-trips)
```

The `s['prefix/']` → sub-store convention is delegated to `dol`. We do **not** reimplement
the `type(self)(**self.__dict__)` trick used by older blob stores.

## What we explicitly do NOT do

- **Auto-detect HNS** — see [design_decisions.md](design_decisions.md). HNS users go to a sibling `azuredatalakedol` package (TBD).
- **`__len__` on `ContainerStore`** — pagination cost is unbounded; offering it would mislead users.
- **Snapshots / versioning / soft delete as Mapping operations** — they're reachable via `BlobHandle` methods.
- **Generate SAS URLs as a Mapping operation** — `BlobHandle.url(expires=...)` is the place for it.
- **Async client** in v1. The same architecture trivially mirrors to `azuredol.aio` later.

## Module layout

```
azuredol/
  __init__.py          # public API re-exports + module docstring
  connection.py        # AzureConnection, resolve_credential
  base.py              # ContainerCollection/Reader/Store, AccountCollection/Reader/Store, BlobHandle
  errors.py            # translate_azure_errors decorator, custom exceptions
  recipes.py           # AzureJsonStore, AzureTextStore, AppendBlobStore, azure_store(...)
  functions.py         # the existing azure_func_service (Azure Functions host launcher)
  testing.py           # Azurite fixture, `with_azurite()` context manager, mk_test_store(...)
  tests/
    test_base.py
    test_recipes.py
    test_connection.py
```

## Backward compatibility

There are no users of `azuredol` yet (confirmed). The refactor is therefore a clean
break. Old names are removed; we do not keep `_old_base.py`.
