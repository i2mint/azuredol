# Azure Blob Storage — Technical Reference for azuredol

A condensed technical reference for contributors. The full citations are kept in this
package's GitHub issues; the goal here is to make the *design choices* in
[architecture.md](architecture.md) and [design_decisions.md](design_decisions.md)
self-contained.

---

## Resource hierarchy

```
Storage Account                        https://{account}.blob.core.windows.net
└── Container (3-63 lowercase chars)   .../{container}
    └── Blob (1-1024 UTF-8 chars)      .../{container}/{blob}
        ↳ '/' inside blob names is purely a prefix convention on flat accounts
        ↳ first-class directories only on HNS (ADLS Gen2) accounts
```

- Unlimited containers per account; unlimited blobs per container.
- Container names: lowercase, digits, `-`, must start/end alphanumeric, no `--`.
- Blob names: case-sensitive, any char (URL-encode reserved ones), 254 path segments on flat / 63 on HNS.
- The root container is `$root`; URLs without an explicit container address it.

## Authentication — what the SDK accepts

| Form | Where to pass it | Notes |
|---|---|---|
| AAD token (`DefaultAzureCredential`, `ManagedIdentityCredential`, …) | `credential=` on every client class | **Microsoft's recommended path.** Same code works for dev laptops, Azure VMs, Functions, AKS via managed identity. |
| Account key (shared key) | `credential="<key>"` (string) or `{"account_name": ..., "account_key": ...}` (dict) | Full account power; no expiry. Riskiest if leaked. |
| SAS token | append to `account_url`, or pass as `credential=` string | Scoped + time-bounded. |
| Connection string | `Client.from_connection_string(...)` | Convenience wrapper around key or SAS. Standard form: `DefaultEndpointsProtocol=https;AccountName=…;AccountKey=…;EndpointSuffix=core.windows.net`. |
| Anonymous | omit `credential` | Only valid for public-read containers. |

All three client classes — `BlobServiceClient`, `ContainerClient`, `BlobClient` — accept the same set.

## Blob types (immutable after creation)

| Property | Block | Append | Page |
|---|---|---|---|
| Max size | ~190.7 TiB | ~195 GiB | 8 TiB |
| Max block / page | 4000 MiB | 4 MiB | 512 B (write up to 4 MiB) |
| Write model | stage blocks → commit, or single-shot `upload_blob` | atomic `append_block` only | `upload_page` at 512-aligned offset |
| Edit | overwrite block / reorder / re-commit | append-only, no edit/delete of blocks | random read/write in fixed allocation |
| Typical use | files, blobs, media, backups | logs, telemetry, audit trails | VHDs / random-access disks |
| SDK enum | `BlobType.BlockBlob` (`upload_blob` default) | `BlobType.AppendBlob` | `BlobType.PageBlob` |

**azuredol default = `BlockBlob`** (see [design_decisions.md](design_decisions.md) §1 for rationale).

## Operations azuredol wraps

All on `ContainerClient` except where noted on `BlobClient`. Exceptions from `azure.core.exceptions`.

| Mapping op | SDK call | Notes |
|---|---|---|
| `__iter__` flat | `container.list_blobs(name_starts_with=prefix)` | Auto-paginated `ItemPaged[BlobProperties]`. `results_per_page=` to tune. |
| Walk hierarchical | `container.walk_blobs(name_starts_with=prefix, delimiter='/')` | Yields `BlobProperties` and `BlobPrefix` (subdir nodes). |
| `__getitem__` full | `blob.download_blob().readall()` | Returns `bytes`. |
| `__getitem__` range | `blob.download_blob(offset=, length=, max_concurrency=)` | `StorageStreamDownloader.chunks()`, `readinto(fp)`. |
| `__setitem__` | `blob.upload_blob(data, overwrite=True, blob_type=…, max_concurrency=…)` | Auto-chunks. Pass `length=` when known. |
| Create-only | `blob.upload_blob(data, overwrite=False)` | Raises `ResourceExistsError` on conflict (good for `setdefault`-style). |
| `__delitem__` | `blob.delete_blob()` or `container.delete_blob(name)` | `delete_snapshots="include"`/`"only"` if snapshots are on. |
| `__contains__` | `blob.exists()` | One network round-trip (HEAD-equivalent). |
| Properties | `blob.get_blob_properties()` | `.size, .last_modified, .etag, .content_settings, .metadata` in one call. |
| Metadata write | `blob.set_blob_metadata({...})` | Replaces all user metadata atomically. |
| Copy | `dst.start_copy_from_url(src_url, requires_sync=…)` | Same-account = sync; cross-account = async (poll `get_blob_properties().copy`). |
| Lease | `blob.acquire_lease(lease_duration=15..60 or -1)` | Returns `BlobLeaseClient`; subsequent ops take `lease=lease`. |
| Conditional | `if_match=etag`, `if_none_match='*'`, `if_modified_since=…` | Optimistic concurrency without leases. |

## Exception → KeyError translation

`azuredol.errors.translate_azure_errors` wraps the Mapping methods and maps:

| Azure exception | Behavior |
|---|---|
| `ResourceNotFoundError` | → `KeyError(k)` for `__getitem__` / `__delitem__`; → `False` for `__contains__`. |
| `ResourceExistsError` | → `BlobAlreadyExistsError(k)` (a `KeyError` subclass) for strict-create flows. |
| `ResourceModifiedError` / `ResourceNotModifiedError` | re-raised (conditional ETag mismatches are caller's problem). |
| `ClientAuthenticationError` | **re-raised untouched**. *Never* swallow as "key absent". |
| `HttpResponseError` | re-raised; `.error_code` carries strings like `"BlobNotFound"`, `"ContainerNotFound"`, `"AuthenticationFailed"`. |
| `ServiceRequestError` / `ServiceResponseError` | re-raised after the SDK's retry budget is exhausted. |

## Performance notes the code must respect

- **Build `BlobServiceClient` once per process.** It owns the HTTP pipeline + connection pool. Derive cheap `ContainerClient` / `BlobClient` from it via `get_container_client(name)` / `get_blob_client(blob)`.
- **`upload_blob` auto-chunks** above ~64 MiB. Pass `max_concurrency=N` for parallel uploads/downloads.
- **Provide `length=`** when uploading from a file — saves a server round-trip and lets the SDK pick single-shot vs chunked optimally.
- **Streaming downloads** via `StorageStreamDownloader.chunks()` cap memory to O(chunk_size).
- **Retries** are built into the SDK pipeline; tune with `retry_total`, `retry_connect`, `retry_read`, `retry_status`, `retry_to_secondary` at *client construction*.

## Pitfalls (encoded in tests where possible)

- **`/` in blob names is convention only** on flat accounts — directories materialise only when `list_blobs` is called with `delimiter='/'`.
- **No native `rename_blob`** on flat accounts — emulate with server-side copy + delete (not atomic).
- **Metadata keys** must be valid C# identifiers (start with letter/`_`, ASCII letters/digits/`_`). Values are ASCII; UTF-8 needs caller-side base64.
- **`exists()` is not free** — it's a round-trip. Prefer `__getitem__`-and-catch-KeyError in tight loops.
- **Soft delete + versioning** make `__delitem__` non-final from a listing perspective. Document loudly when present on the account.
- **Append blob writes from different processes** interleave at block granularity unless leased — they never tear within a block, but ordering is server-side only.

## Local testing — Azurite

```bash
docker run -p 10000:10000 -p 10001:10001 -p 10002:10002 \
  mcr.microsoft.com/azure-storage/azurite
```

Default credentials (the same on every Azurite instance):

```
AccountName: devstoreaccount1
AccountKey:  Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==

Shorthand for the SDK: connection_string="UseDevelopmentStorage=true"
```

Azurite **does not** support: Azure Files, ADLS Gen2 / HNS, object replication, change feed, blob inventory. Error messages may differ from the cloud. Plenty for unit and integration tests against azuredol's surface.

## Related blob-shaped services (out of scope for azuredol)

| Service | SDK | One-liner |
|---|---|---|
| Azure Files | `azure-storage-file-share` | SMB/NFS-mounted shares; mount-as-network-drive workloads. |
| Azure Data Lake Storage Gen2 | `azure-storage-file-datalake` | Blob + HNS; analytics-shaped. Sibling package material. |
| Azure Queue Storage | `azure-storage-queue` | FIFO-ish messages ≤ 64 KiB. Different mental model. |
| Azure Table Storage / Cosmos Table API | `azure-data-tables` | Row-shaped NoSQL. Different mental model. |
