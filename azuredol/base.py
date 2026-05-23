"""Close-to-metal Mapping stores over Azure Blob Storage.

Three concrete classes:

- ``ContainerStore`` — the primary store. Mapping of blob name → bytes within one container.
- ``AccountStore`` — mapping of container name → ``ContainerStore`` within one account.
- ``BlobHandle``  — non-Mapping escape hatch for one blob with the full Azure surface.

See ``misc/docs/architecture.md`` Layer B. Codec / convenience layers live in
``azuredol.recipes``; the connection layer lives in ``azuredol.connection``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional, Union

from azure.storage.blob import (
    BlobClient,
    BlobServiceClient,
    BlobType,
    ContainerClient,
    ContentSettings,
    generate_blob_sas,
    BlobSasPermissions,
)

from dol import KvReader, KvPersister

from azuredol.connection import AzureConnection
from azuredol.errors import (
    BlobNotFoundError,
    ContainerAlreadyExistsError,
    ContainerNotEmptyError,
    ContainerNotFoundError,
    translate_azure_errors,
)


# ---------------------------------------------------------------------------
# ContainerStore — the primary store
# ---------------------------------------------------------------------------


class _ContainerStoreBase:
    """Shared init / repr for the ContainerStore family.

    Held separate from ``KvReader`` so the same init can back the read-only,
    read-write, and append-only variants.
    """

    def __init__(
        self,
        container: Union[str, ContainerClient],
        *,
        prefix: str = "",
        connection: Union[AzureConnection, BlobServiceClient, str, dict, None] = None,
        create_container_if_missing: bool = False,
        blob_type: BlobType = BlobType.BlockBlob,
        upload_kwargs: Optional[dict] = None,
        download_kwargs: Optional[dict] = None,
    ):
        """Build a store scoped to one container (and optional prefix).

        Args:
            container: An existing ``ContainerClient`` (used as-is) or a container
                name string (resolved via ``connection``).
            prefix: A blob-name prefix that all keys are scoped under. Trailing slash
                is normalised in.
            connection: An ``AzureConnection``, a ``BlobServiceClient``, a connection
                string, a kwargs dict, or ``None`` (defer to env / AAD). Ignored if
                ``container`` is already a ``ContainerClient``.
            create_container_if_missing: If True and the container does not exist,
                create it on first use.
            blob_type: Default blob type for writes. ``BlockBlob`` per
                ``misc/docs/design_decisions.md`` §1.
            upload_kwargs: Extra kwargs forwarded to ``BlobClient.upload_blob`` on writes.
            download_kwargs: Extra kwargs forwarded to ``BlobClient.download_blob`` on reads.
        """
        if isinstance(container, ContainerClient):
            self._container_client = container
            self._connection = None
        else:
            self._connection = AzureConnection.from_anything(connection)
            self._container_client = self._connection.container_client(container)

        self.container_name = self._container_client.container_name
        self.prefix = f"{prefix.strip('/')}/" if prefix else ""
        self.blob_type = blob_type
        self.upload_kwargs = dict(upload_kwargs or {})
        self.download_kwargs = dict(download_kwargs or {})
        self.create_container_if_missing = create_container_if_missing

        if create_container_if_missing and not self._container_client.exists():
            self._container_client.create_container()

    # ---- key <-> id translation ----

    def _id_of_key(self, k: str) -> str:
        return f"{self.prefix}{k}"

    def _key_of_id(self, _id: str) -> str:
        return _id[len(self.prefix) :] if self.prefix else _id

    # ---- repr ----

    def __repr__(self) -> str:
        bits = [repr(self.container_name)]
        if self.prefix:
            bits.append(f"prefix={self.prefix!r}")
        if self.blob_type != BlobType.BlockBlob:
            bits.append(f"blob_type={self.blob_type!s}")
        return f"{self.__class__.__name__}({', '.join(bits)})"

    # ---- internal: derive a sibling store with adjusted attrs ----

    def _with(self, **overrides) -> "_ContainerStoreBase":
        """Build a new instance of the same class with overridden init kwargs.

        Used by the trailing-slash sub-store convention. Carries the underlying
        ``ContainerClient`` over to avoid re-resolving credentials.
        """
        kw = dict(
            container=self._container_client,
            prefix=overrides.pop("prefix", self.prefix),
            connection=None,
            create_container_if_missing=False,
            blob_type=overrides.pop("blob_type", self.blob_type),
            upload_kwargs=overrides.pop("upload_kwargs", dict(self.upload_kwargs)),
            download_kwargs=overrides.pop(
                "download_kwargs", dict(self.download_kwargs)
            ),
        )
        kw.update(overrides)
        return type(self)(**kw)


class ContainerCollection(_ContainerStoreBase, KvReader):
    """Iteration / membership / cardinality (`__len__` deliberately omitted) over a container.

    ``__len__`` is intentionally NOT implemented — see
    ``misc/docs/design_decisions.md`` §2. Pagination cost is unbounded; users wanting
    a count call ``sum(1 for _ in store)``.
    """

    def __iter__(self) -> Iterator[str]:
        for blob in self._container_client.list_blobs(name_starts_with=self.prefix):
            yield self._key_of_id(blob.name)

    @translate_azure_errors(key_arg=1)
    def __contains__(self, k: str) -> bool:
        return self._container_client.get_blob_client(self._id_of_key(k)).exists()

    # Per design_decisions.md §2: do NOT implement __len__ on the metal store.
    # ``Mapping.__len__`` is inherited from ABC and would raise NotImplementedError;
    # we explicitly delete it so ``len(store)`` raises ``TypeError`` (matching dict-of-
    # unknown-size semantics in Python).
    def __len__(self):
        raise TypeError(
            f"{type(self).__name__} does not implement __len__ (unbounded pagination "
            "cost). Use `sum(1 for _ in store)` if you accept the scan cost."
        )

    def walk(self, delimiter: str = "/") -> Iterator[Any]:
        """Hierarchical walk yielding either ``BlobProperties`` or ``BlobPrefix`` nodes.

        Thin pass-through to ``ContainerClient.walk_blobs``. Useful for tree-shaped
        listings; not part of the Mapping interface.
        """
        return self._container_client.walk_blobs(
            name_starts_with=self.prefix, delimiter=delimiter
        )


class ContainerReader(ContainerCollection):
    """Adds ``__getitem__`` (returns bytes) over ``ContainerCollection``.

    The trailing-slash sub-store convention lives here: ``store['sub/']`` returns a new
    ``ContainerReader`` with extended prefix and zero round-trips.
    """

    @translate_azure_errors(key_arg=1, not_found_cls=BlobNotFoundError)
    def __getitem__(self, k: str) -> bytes:
        # Trailing-slash sub-store convention.
        if isinstance(k, str) and k.endswith("/"):
            return self._with(prefix=self._id_of_key(k))
        blob_client = self._container_client.get_blob_client(self._id_of_key(k))
        return blob_client.download_blob(**self.download_kwargs).readall()


class ContainerStore(ContainerReader, KvPersister):
    """The primary read-write Mapping over an Azure container.

    Doctest below requires Azurite (or live Azure). It is shown but not auto-run.

    Example (requires Azurite):

        >>> from azuredol import ContainerStore
        >>> s = ContainerStore(  # doctest: +SKIP
        ...     'my-test-container',
        ...     connection='UseDevelopmentStorage=true',
        ...     create_container_if_missing=True,
        ... )
        >>> s['k1'] = b'v1'                     # doctest: +SKIP
        >>> s['k1']                              # doctest: +SKIP
        b'v1'
        >>> 'k1' in s                            # doctest: +SKIP
        True
        >>> del s['k1']                          # doctest: +SKIP

    For unit tests without Azurite, prototype with ``dol``'s in-memory pattern:
    ``wrap_kvs(dict(), ...)``.
    """

    @translate_azure_errors(key_arg=1)
    def __setitem__(self, k: str, v) -> None:
        blob_client = self._container_client.get_blob_client(self._id_of_key(k))
        # Default to overwrite=True per design_decisions.md §7.
        kwargs = {"overwrite": True, "blob_type": self.blob_type, **self.upload_kwargs}
        blob_client.upload_blob(v, **kwargs)

    @translate_azure_errors(key_arg=1, not_found_cls=BlobNotFoundError)
    def __delitem__(self, k: str) -> None:
        blob_client = self._container_client.get_blob_client(self._id_of_key(k))
        blob_client.delete_blob()


# ---------------------------------------------------------------------------
# BlobHandle — non-Mapping escape hatch for a single blob
# ---------------------------------------------------------------------------


class BlobHandle:
    """Thin facade over one ``BlobClient``. Not a Mapping.

    Use when you need the full Azure-blob surface for a single blob: metadata,
    properties, conditional writes, leases, copy, append, SAS URL generation,
    streaming downloads.

    Args:
        container: An existing ``ContainerClient`` or a container name string.
        blob: The blob name (relative to the container root; full path including '/').
        connection: Ignored if ``container`` is a ``ContainerClient``. Otherwise
            resolved via ``AzureConnection.from_anything``.
    """

    def __init__(
        self,
        container: Union[str, ContainerClient],
        blob: str,
        *,
        connection: Union[AzureConnection, BlobServiceClient, str, dict, None] = None,
    ):
        if isinstance(container, ContainerClient):
            self._container_client = container
            self._connection = None
        else:
            self._connection = AzureConnection.from_anything(connection)
            self._container_client = self._connection.container_client(container)
        self.container_name = self._container_client.container_name
        self.blob = blob

    @property
    def client(self) -> BlobClient:
        return self._container_client.get_blob_client(self.blob)

    def __repr__(self) -> str:
        return f"BlobHandle({self.container_name!r}, {self.blob!r})"

    # ---- core ops ----

    def read(self, *, offset: Optional[int] = None, length: Optional[int] = None) -> bytes:
        """Download (possibly a range) and return bytes."""
        return self.client.download_blob(offset=offset, length=length).readall()

    def download_stream(self, *, chunk_size: Optional[int] = None):
        """Return a streaming downloader. Iterate chunks via ``.chunks()`` or ``.readinto(fp)``."""
        return self.client.download_blob()

    @translate_azure_errors(key_arg="blob")
    def write(
        self,
        data,
        *,
        blob_type: BlobType = BlobType.BlockBlob,
        overwrite: bool = True,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        **kwargs,
    ) -> None:
        """Upload data; default overwrite=True for ``MutableMapping`` symmetry."""
        if content_type is not None:
            kwargs["content_settings"] = ContentSettings(content_type=content_type)
        if metadata is not None:
            kwargs["metadata"] = metadata
        self.client.upload_blob(data, blob_type=blob_type, overwrite=overwrite, **kwargs)

    def create(self, data, *, overwrite: bool = False, **kwargs) -> None:
        """Strict-create variant of ``write``; raises ``BlobAlreadyExistsError`` on conflict."""
        self.write(data, overwrite=overwrite, **kwargs)

    @translate_azure_errors(key_arg="blob")
    def append(self, data) -> None:
        """Append bytes to an append-blob (creating it if absent)."""
        client = self.client
        if not client.exists():
            client.create_append_blob()
        # 4 MiB block limit on append blobs.
        block_size = 4 * 1024 * 1024
        v = data.encode() if isinstance(data, str) else bytes(data)
        for i in range(0, len(v), block_size):
            block = v[i : i + block_size]
            client.append_block(block, length=len(block))

    @translate_azure_errors(key_arg="blob")
    def delete(self) -> None:
        self.client.delete_blob()

    def exists(self) -> bool:
        return self.client.exists()

    @translate_azure_errors(key_arg="blob")
    def properties(self):
        """Return ``BlobProperties`` (size, last_modified, etag, content_settings, metadata, …)."""
        return self.client.get_blob_properties()

    def copy_from(self, source_url: str, *, requires_sync: Optional[bool] = None):
        """Server-side copy from a URL. Same-account = sync; cross-account = async (poll)."""
        return self.client.start_copy_from_url(source_url, requires_sync=requires_sync)

    def acquire_lease(self, lease_duration: int = -1):
        """Acquire a lease (15-60s, or -1 for infinite). Returns a ``BlobLeaseClient``."""
        return self.client.acquire_lease(lease_duration=lease_duration)

    def url(self, *, expires_in: Optional[timedelta] = None) -> str:
        """Return the blob URL.

        If ``expires_in`` is set and the underlying credential is a shared-key, a SAS
        URL with read permission is generated. Otherwise the plain blob URL is returned
        (which is only useful for public containers or pre-shared SAS contexts).
        """
        client = self.client
        if expires_in is None:
            return client.url
        # SAS generation requires the account key. Pull from the service client.
        try:
            account_key = client.credential.account_key  # type: ignore[attr-defined]
        except AttributeError as e:
            raise ValueError(
                "SAS URL generation requires a shared-key credential on this client. "
                "Use a connection string or account_key= when constructing the store, or "
                "generate the SAS upstream via azure.identity user-delegation flows."
            ) from e
        sas = generate_blob_sas(
            account_name=client.account_name,
            container_name=client.container_name,
            blob_name=client.blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + expires_in,
        )
        return f"{client.url}?{sas}"


# ---------------------------------------------------------------------------
# AccountStore — mapping of container name → ContainerStore
# ---------------------------------------------------------------------------


class _AccountStoreBase:
    """Shared init/repr for the AccountStore family."""

    def __init__(
        self,
        connection: Union[AzureConnection, BlobServiceClient, str, dict, None] = None,
        *,
        container_store_cls: type = None,
        container_store_kwargs: Optional[dict] = None,
    ):
        self._connection = AzureConnection.from_anything(connection)
        self._service_client = self._connection.service_client
        self._container_store_cls = container_store_cls or ContainerStore
        self._container_store_kwargs = dict(container_store_kwargs or {})

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(account={self._service_client.account_name!r})"


class AccountCollection(_AccountStoreBase, KvReader):
    """Mapping over container names in an account (iter / contains / len)."""

    def __iter__(self) -> Iterator[str]:
        for c in self._service_client.list_containers():
            yield c.name

    def __contains__(self, k: str) -> bool:
        return self._service_client.get_container_client(k).exists()

    def __len__(self) -> int:
        # Containers per account are small (administrative resource) — counting is cheap.
        return sum(1 for _ in self)


class AccountReader(AccountCollection):
    """Adds ``__getitem__`` returning a ``ContainerStore`` (or configured subclass)."""

    def __getitem__(self, k: str):
        cc = self._service_client.get_container_client(k)
        if not cc.exists():
            raise ContainerNotFoundError(k)
        return self._container_store_cls(cc, **self._container_store_kwargs)


class AccountStore(AccountReader, KvPersister):
    """Read-write Mapping over containers in an account.

    ``__setitem__`` creates a container; the value is ignored except when it's a
    Mapping (in which case it is treated as an initial bulk-load).

    ``__delitem__`` refuses non-empty containers — call ``self.delete(name, force=True)``
    to acknowledge a cascading delete. See ``misc/docs/design_decisions.md`` §12.
    """

    def __setitem__(self, k: str, v=None) -> None:
        cc = self._service_client.get_container_client(k)
        if cc.exists():
            raise ContainerAlreadyExistsError(k)
        cc.create_container()
        if v:
            # Bulk-load convenience: if v is a Mapping, populate.
            store = self._container_store_cls(cc, **self._container_store_kwargs)
            try:
                items = v.items()
            except AttributeError:
                return
            for bk, bv in items:
                store[bk] = bv

    def __delitem__(self, k: str) -> None:
        cc = self._service_client.get_container_client(k)
        if not cc.exists():
            raise ContainerNotFoundError(k)
        # Refuse non-empty containers; force-delete is opt-in via .delete(name, force=True).
        try:
            next(iter(cc.list_blobs(results_per_page=1)))
            raise ContainerNotEmptyError(
                f"Container {k!r} is not empty. Call "
                f"`account_store.delete({k!r}, force=True)` to cascade-delete its blobs."
            )
        except StopIteration:
            pass
        cc.delete_container()

    def delete(self, k: str, *, force: bool = False) -> None:
        """Delete a container; if ``force=True``, cascade-delete any blobs first."""
        cc = self._service_client.get_container_client(k)
        if not cc.exists():
            raise ContainerNotFoundError(k)
        if force:
            for blob in cc.list_blobs():
                cc.delete_blob(blob.name)
        cc.delete_container()
