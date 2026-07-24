---
name: azuredol
description: Use when developing, reviewing, or extending the azuredol package (Azure Blob Storage as dol Mapping interfaces). Triggers on edits under i/azuredol/, on imports of `azuredol`, when adding new blob-store wrappers, value codecs, or credential paths, when writing tests against Azurite, when reviewing PRs against azuredol, and when designing sibling packages like azuredatalakedol.
---

# azuredol — Developer & Agent Skill

`azuredol` exposes **Azure Blob Storage** as `dol`-style `Mapping` / `MutableMapping`
interfaces. This skill is the working memory: when modifying or extending the package,
read this first, then dive into the [misc/docs/](../../../misc/docs/) trio that this
file distills.

**Source of truth** (always defer to these):

- `misc/docs/architecture.md` — the 3-layer design and class hierarchy.
- `misc/docs/azure_blob_reference.md` — Azure Blob SDK & service facts.
- `misc/docs/design_decisions.md` — every defaulted choice with rationale.

---

## Mental model in one diagram

```
azuredol.recipes        ← codec layers, mk_azure_store(...) one-call factory
azuredol.base           ← AccountStore, ContainerStore, BlobHandle (close-to-metal, bytes)
azuredol.connection     ← AzureConnection: credential cascade, lazy BlobServiceClient
azuredol.errors         ← @translate_azure_errors decorator, custom KeyError subclasses
azuredol.functions      ← azure_func_service (Azure Functions host launcher; unrelated to blobs)
azuredol.testing        ← Azurite fixture, mk_test_store(...)
```

The primary store is **`ContainerStore`** — one mapping per Azure container. `AccountStore`
is a mapping-of-containers; `BlobHandle` is a non-Mapping escape hatch for one blob.

## Non-negotiable rules

1. **`dol`-house base classes only.** Subclass `KvReader` / `KvPersister` from `dol.base`, never `Mapping` / `MutableMapping` directly. (See `dol/.claude/rules/dol-conventions.md`.)
2. **Default blob type is `BlockBlob`.** Append blobs cap at 195 GiB and cannot replace content — that breaks `MutableMapping` semantics. Append remains opt-in via `blob_type=BlobType.AppendBlob` or `recipes.AppendBlobStore`.
3. **No `__len__` on `ContainerStore`.** Pagination cost is unbounded. Users wanting a count call `sum(1 for _ in store)` and own the cost.
4. **All Azure-exception catches happen in `errors.py`.** Every Mapping method on a close-to-metal store is wrapped with `@translate_azure_errors`; nothing else catches `azure.core.exceptions.*`. Auth errors *never* translate to "key absent".
5. **`overwrite=True` is the default** on `__setitem__`. Dict semantics demand it. Strict-create is `BlobHandle.create(data, overwrite=False)`.
6. **Sub-stores use `mk_relative_path_store(prefix_attr='prefix')`** from `dol.paths`. Do NOT reinvent the `type(self)(**self.__dict__)` pattern from s3dol.
7. **Polymorphic constructor inputs.** Public constructors accept the thing or a spec for it (string container name → resolve via `connection.resolve_credential`; existing `ContainerClient` → used as-is; dict → built from kwargs).
8. **No global mutable state.** No module-level `BlobServiceClient`. Connection re-use is a recipe-layer concern (`mk_azure_store(..., reuse_connection=True)`, defaulting to `True`, opt-out documented).
9. **HNS / ADLS Gen2 is out of scope.** Sibling package `azuredatalakedol` (TBD). Do NOT auto-detect HNS inside azuredol.
10. **No silent destruction.** `del account_store['container']` refuses non-empty containers; `account_store.delete('container', force=True)` is the explicit purge.

## Adding a new value codec / key transform

Layer C only. Never subclass `ContainerStore` to add a codec — use `dol`'s composition tools:

```python
from dol import wrap_kvs, KeyCodecs, ValueCodecs, Pipe
from azuredol.base import ContainerStore

# Right way: compose
AzureJsonStore = wrap_kvs(ContainerStore, value_codec=ValueCodecs.json())
AzureJsonFiles = Pipe(KeyCodecs.suffixed(".json"), ValueCodecs.json())(ContainerStore)


# Wrong way: subclass
class AzureJsonStore(ContainerStore):  # don't do this
    def __getitem__(self, k):
        return json.loads(super().__getitem__(k))
```

When `obj_of_data` would be `bytes.decode`, write `lambda b: b.decode()` — known dol
signature-inference bug (dol issue #9).

## Adding a new connection path / credential type

`azuredol.connection.resolve_credential(...)` is the single place. Extend its cascade,
update `design_decisions.md` §6, and add a test in `tests/test_connection.py` that
exercises the new branch.

The cascade is documented in `design_decisions.md` §6 and `architecture.md` Layer A.

## Adding to the metal layer (rarely needed)

If you must add behavior to `ContainerStore` itself (e.g. a new SDK feature like a new
blob operation):

- Add to **`BlobHandle`** first if it's per-blob — that's the non-Mapping escape hatch.
- Add a Mapping method only when it's genuinely Mapping-shaped.
- Wrap with `@translate_azure_errors(key_arg=...)` for any path that touches a blob.
- Update `architecture.md` (Contracts table) and `azure_blob_reference.md`.

## Testing protocol

1. **Prototype with `dict()`** wherever a transform is under test in isolation (the dol convention).
2. **Integration tests** require Azurite. Use the `azurite_connection` pytest fixture (in `azuredol/testing.py`); tests are skipped with a clear message if Docker is unavailable.
3. **Doctests** in module docstrings stay runnable — they are part of the documentation surface (`pyproject.toml` enables doctest `NORMALIZE_WHITESPACE` + `ELLIPSIS`).
4. **Live Azure tests** are gated by env var `AZURE_LIVE_TEST_CONNECTION_STRING`; never run in CI by default.

## Spinning up Azurite locally

```bash
docker run -p 10000:10000 -p 10001:10001 -p 10002:10002 \
  mcr.microsoft.com/azure-storage/azurite
```

Connection string: `"UseDevelopmentStorage=true"` (SDK shorthand) or the full default-credentials string in `azure_blob_reference.md` §Local testing.

Azurite does **not** support: Azure Files, ADLS Gen2 / HNS, object replication, change feed, blob inventory. Don't write tests that depend on those features.

## Common operations cheatsheet

| Want to... | Use |
|---|---|
| Plain bytes mapping over a container | `ContainerStore(container_client_or_name)` |
| Bytes mapping scoped to a prefix | `ContainerStore(name, prefix='logs/')` |
| JSON-typed values | `wrap_kvs(ContainerStore, value_codec=ValueCodecs.json())` |
| Text-typed values | `wrap_kvs(ContainerStore, obj_of_data=lambda b: b.decode(), data_of_obj=lambda s: s.encode())` |
| Append-only (log) blobs | `recipes.AppendBlobStore(container_name)` or `ContainerStore(..., blob_type=BlobType.AppendBlob)` |
| Stream a large blob | `BlobHandle(container, blob).download_stream(chunk_size=...)` |
| Pre-signed URL | `BlobHandle(container, blob).url(expires_in=timedelta(minutes=15))` |
| Iterate containers in an account | `for name in AccountStore(connection): ...` |
| One-call factory for a typed store | `recipes.mk_azure_store(container='...', prefix='...', value_codec=...)` |

## When in doubt

- Defaults always lean Mapping-faithful (`overwrite=True`, `BlockBlob`, KeyError on missing).
- Costs always lean visible (no auto-len, no `exists()`-then-`get()` patterns, no global caches).
- Surface always leans `dol`-composable (wrap_kvs over subclasses, codecs over methods).

When changing a default, update `design_decisions.md` in the **same** PR. The doc IS the
contract.
