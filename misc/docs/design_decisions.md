# azuredol — Design Decisions

Every defaulted choice with a one-paragraph rationale. When in doubt about *why* the code
is the way it is, this is the doc to read. When changing a default, update this doc in the
same PR.

---

## 1. Default blob type is `BlockBlob`, not `AppendBlob`

The pre-refactor azuredol defaulted to **append** blobs (created via `create_append_blob()`
and written via `append_block`). The new default is **block**.

**Why block:**

- `MutableMapping.__setitem__` semantically replaces the value. Append blobs cannot replace content; "replace" means delete-then-recreate, which breaks atomicity and lets concurrent readers see an empty interlude.
- Append blobs cap at **195 GiB**. Block blobs cap at ~190 TiB. A surprise 195 GiB ceiling is the wrong failure mode for an "object store".
- Most third-party tooling (AzCopy, Storage Explorer, ADLS Gen2 readers) is block-blob-centric.
- Single-shot `upload_blob(data, overwrite=True)` on a block blob is service-atomic from the reader's perspective (the ETag flips at commit). No staging dance is needed for typical payloads.
- The SDK auto-chunks and parallelises block uploads, so payload size is not an argument for append blobs.
- `BlobType.BlockBlob` is the SDK's own default for `upload_blob`.

**Append remains a first-class opt-in:**

- `ContainerStore(container, blob_type=BlobType.AppendBlob)` — per-instance override.
- `recipes.AppendBlobStore = partial(ContainerStore, blob_type=BlobType.AppendBlob)` — named alias.
- `BlobHandle.append(data)` — per-blob method, lets the caller mix block and append in one store.

## 2. `__len__` is intentionally not implemented on `ContainerStore`

`list_blobs` pagination has unbounded cost (containers can hold billions of blobs). Implementing `__len__` would mislead users into writing `len(store)` calls that occasionally explode.

We:

- Do **not** implement `__len__` at all on `ContainerStore`. Calling `len(store)` raises `TypeError` (Python's default).
- Document the workaround: `sum(1 for _ in store)` — the user explicitly opts into the scan.
- `AccountStore.__len__` is fine — number of containers per account is small.

## 3. `__contains__` uses `BlobClient.exists()` (one round-trip)

The alternative is "try `__getitem__` and catch `KeyError`," which is cheaper *if you were going to read anyway*. For pure existence checks, `exists()` is one HEAD-equivalent call — the right primitive.

Power users in hot loops should branch on the cached `BlobHandle` and use try/except. We do not optimise the Mapping `__contains__` for that case.

## 4. Single error-translation decorator

`@translate_azure_errors` is the **only** place in the metal layer that catches Azure exceptions. Every other code path lets them propagate. This keeps:

- Error semantics auditable from one file (`errors.py`).
- The `__getitem__` / `__setitem__` / `__delitem__` bodies tiny and readable.
- The "auth error vs not-found" distinction crisp: auth errors *always* re-raise; only `ResourceNotFoundError` translates.

## 5. Sub-stores use `mk_relative_path_store(prefix_attr='prefix')`

The legacy s3dol-style trick `type(self)(**self.__dict__)` is fragile (breaks the moment any attr isn't an `__init__` arg). `dol`'s `mk_relative_path_store` is the canonical mechanism and gives us `s['prefix/']` → sub-store with zero round-trips.

## 6. Polymorphic credential input

Like `mongodol` and `chromadol`, every public constructor accepts the **thing or a spec for it**:

```python
ContainerStore(container_client)             # already-built ContainerClient → used as-is
ContainerStore("mycontainer")                # bare string → resolve credential, build it
ContainerStore({"container": "...", ...})    # dict → build it from kwargs
```

The `azuredol.connection.resolve_credential(...)` cascade is the single source of truth.

## 7. `overwrite=True` is the default on `__setitem__`

Dict semantics say `s[k] = v` always succeeds. The Azure SDK defaults `upload_blob` to `overwrite=False`. We flip the default to match Python's Mapping contract. The strict-create variant is `store.setdefault(k, v)` or `BlobHandle.create(data, overwrite=False)` — explicit opt-in.

## 8. HNS / ADLS Gen2 is out of scope for `azuredol`

HNS-enabled accounts have first-class directories, atomic renames, POSIX ACLs — none of which `azure-storage-blob` exposes cleanly. The right SDK is `azure-storage-file-datalake`, with a parallel resource model (`DataLakeServiceClient → FileSystemClient → DirectoryClient → FileClient`).

Doing auto-detection inside `azuredol` would:

- Bring `azure-storage-file-datalake` into the dependency set for every user.
- Blur error semantics (different exception shapes, different listing semantics).
- Be silently wrong on accounts where the user *wanted* the flat semantics on an HNS account.

The plan is a sibling package — tentatively `azuredatalakedol` — that wraps the datalake SDK with the same `dol`-style facade and shares `azuredol.connection`'s credential cascade.

## 9. Class naming avoids "Bucket"

S3 calls the top-level grouping a "bucket"; Azure calls it a "container". We mirror Azure's vocabulary. The Cosmos DB package (`cosmodol`) faces a worse collision (Cosmos also uses "container" for its sharded item collection) and *adds* the `Cosmos` prefix; we don't need that here because Azure Blob is the only Azure-blob-ish service in the user's `dol` ecosystem.

## 10. No global mutable state

No module-level `BlobServiceClient` cache. No process-wide credential cache beyond what the Azure SDK itself does. Every `AzureConnection` owns its `BlobServiceClient`. Tests that need isolation simply build a fresh `AzureConnection`.

Connection re-use is a *user-level* concern — the recipe layer's `azure_store(...)` factory caches per-(account, container) within a single process via `functools.lru_cache` on the underlying connection builder, but that cache is opt-out (`azure_store(..., reuse_connection=False)`) and is documented.

## 11. Reader-only classes are real

`ContainerReader`, `AccountReader`, `ContainerCollection`, `AccountCollection` exist as
separate classes — not just as "the Store with `__setitem__` deleted". This matches the
`KvReader` / `KvPersister` distinction in `dol.base` and lets:

- Static analysers catch `store[k] = v` calls on a read-only store at type-check time.
- A read-only credential (anonymous public container, scoped SAS) refuse to even attempt a write.
- A future `azuredol.aio` mirror split the same way.

## 12. `__delitem__` on `AccountStore` will NOT auto-empty a container

s3dol's `S3ClientDol.__delitem__` deletes every blob in the bucket then the bucket itself.
This is convenient and *dangerous*. We refuse it:

```python
del account_store["container_name"]  # → raises if container is not empty
account_store.delete("container_name", force=True)  # explicit, documented
```

## 13. `azure_func_service` (Azure Functions) lives in `functions.py`, unchanged

It is unrelated to the Blob Storage adapter, but it's a small useful tool. We keep it in
the package rather than spinning it out (one-file modules don't earn their own package).
Future Azure-Functions tooling can grow alongside it.

## 14. Testing strategy

- **Unit tests** prototype with `dict()` as backend wherever a transform is being tested in isolation (the `dol` convention).
- **Integration tests** require Azurite. A `pytest` fixture (`azurite_connection`) launches Azurite via Docker if available, otherwise the tests are skipped with a clear message.
- **Live-Azure tests** are gated by env var `AZURE_LIVE_TEST_CONNECTION_STRING`; never run in CI by default.

## 15. Async support is deferred to v2

The architecture is sync mirror-able trivially (every SDK class has an `.aio` twin with the
same method names). We don't ship async in v1 — the first job is to make the sync surface
right.
