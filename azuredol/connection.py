"""Connection-layer for azuredol.

Owns the expensive resource (``BlobServiceClient``) and the credential cascade.
See ``misc/docs/architecture.md`` Layer A and ``misc/docs/design_decisions.md`` §6.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Optional, Union

from azure.storage.blob import BlobServiceClient


CredentialLike = Union[str, dict, Any, None]
"""Any of: account-key string, connection string, SAS string, dict of kwargs,
``azure.identity`` credential object, or None (defer to env / DefaultAzureCredential)."""


# Env vars consulted by ``resolve_credential``.
_ENV_CONNECTION_STRING = "AZURE_STORAGE_CONNECTION_STRING"
_ENV_ACCOUNT_URL = "AZURE_STORAGE_ACCOUNT_URL"
_ENV_ACCOUNT_KEY = "AZURE_STORAGE_ACCOUNT_KEY"


def _looks_like_connection_string(s: str) -> bool:
    """Connection strings contain `;`-separated `key=value` pairs and include either
    ``AccountName=`` or ``DefaultEndpointsProtocol=``."""
    return ("AccountName=" in s or "DefaultEndpointsProtocol=" in s) and "=" in s


def resolve_credential(
    *,
    credential: CredentialLike = None,
    connection_string: Optional[str] = None,
    account_url: Optional[str] = None,
    account_key: Optional[str] = None,
) -> dict:
    """Resolve a credential into a normalized form that can build a ``BlobServiceClient``.

    Cascade (first hit wins):

    1. Explicit ``credential=``
    2. Explicit ``connection_string=``
    3. Explicit ``account_url=`` + ``account_key=`` (or just ``account_url=`` + AAD)
    4. Env var ``AZURE_STORAGE_CONNECTION_STRING``
    5. Env vars ``AZURE_STORAGE_ACCOUNT_URL`` + ``AZURE_STORAGE_ACCOUNT_KEY``
    6. Env var ``AZURE_STORAGE_ACCOUNT_URL`` alone + ``DefaultAzureCredential``

    Returns:
        A dict with one of these shapes:
            ``{"conn_str": "..."}``                            # for from_connection_string
            ``{"account_url": "...", "credential": <obj>}``    # for __init__

    Raises:
        ValueError: if no source resolves.
    """
    # 1. Explicit credential (with optional account_url)
    if credential is not None:
        # If credential is a connection-string-shaped string, treat it as such.
        if isinstance(credential, str) and _looks_like_connection_string(credential):
            return {"conn_str": credential}
        if account_url is None:
            account_url = os.environ.get(_ENV_ACCOUNT_URL)
        if account_url is None:
            raise ValueError(
                "credential=... was provided but no account_url. Pass account_url=... or "
                f"set the {_ENV_ACCOUNT_URL} env var."
            )
        return {"account_url": account_url, "credential": credential}

    # 2. Explicit connection string
    if connection_string is not None:
        return {"conn_str": connection_string}

    # 3. Explicit account_url + account_key
    if account_url is not None and account_key is not None:
        return {"account_url": account_url, "credential": account_key}
    if account_url is not None:
        return {"account_url": account_url, "credential": _default_aad_credential()}

    # 4. Env: connection string
    env_cs = os.environ.get(_ENV_CONNECTION_STRING)
    if env_cs:
        return {"conn_str": env_cs}

    # 5. Env: account_url + account_key
    env_url = os.environ.get(_ENV_ACCOUNT_URL)
    env_key = os.environ.get(_ENV_ACCOUNT_KEY)
    if env_url and env_key:
        return {"account_url": env_url, "credential": env_key}

    # 6. Env: account_url alone + AAD
    if env_url:
        return {"account_url": env_url, "credential": _default_aad_credential()}

    raise ValueError(
        "Could not resolve Azure credentials. Provide one of:\n"
        "  - credential=<obj or string>\n"
        "  - connection_string=<str>\n"
        "  - account_url=<url> + account_key=<key>\n"
        "  - env var AZURE_STORAGE_CONNECTION_STRING\n"
        "  - env vars AZURE_STORAGE_ACCOUNT_URL + AZURE_STORAGE_ACCOUNT_KEY\n"
        "  - env var AZURE_STORAGE_ACCOUNT_URL alone (uses DefaultAzureCredential)\n"
    )


def _default_aad_credential():
    """Lazy import to keep ``azure-identity`` an optional dependency."""
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as e:
        raise ImportError(
            "azure-identity is required for AAD credentials. Install with: "
            "`pip install azure-identity`"
        ) from e
    return DefaultAzureCredential()


@dataclass
class AzureConnection:
    """Holds a resolved credential and a lazy ``BlobServiceClient``.

    This is the dependency-injection seam for the whole package. Tests construct one
    pointing at Azurite without touching any store class.

    Args:
        credential: explicit credential object, key string, or SAS string.
        connection_string: full connection string (overrides ``credential``).
        account_url: storage account URL (with or without credential).
        account_key: shared-key for the account.

    All four args are optional; the credential cascade in
    ``resolve_credential`` is consulted if none are provided.
    """

    credential: CredentialLike = None
    connection_string: Optional[str] = None
    account_url: Optional[str] = None
    account_key: Optional[str] = None
    client_kwargs: dict = field(default_factory=dict)

    @cached_property
    def _resolved(self) -> dict:
        return resolve_credential(
            credential=self.credential,
            connection_string=self.connection_string,
            account_url=self.account_url,
            account_key=self.account_key,
        )

    @cached_property
    def service_client(self) -> BlobServiceClient:
        """The lazily-constructed ``BlobServiceClient``. Cached for the connection's lifetime."""
        r = self._resolved
        if "conn_str" in r:
            return BlobServiceClient.from_connection_string(
                r["conn_str"], **self.client_kwargs
            )
        return BlobServiceClient(
            account_url=r["account_url"],
            credential=r["credential"],
            **self.client_kwargs,
        )

    def container_client(self, container: str):
        """Cheap derivation of a ``ContainerClient`` from the shared service client."""
        return self.service_client.get_container_client(container)

    def blob_client(self, container: str, blob: str):
        """Cheap derivation of a ``BlobClient`` from the shared service client."""
        return self.service_client.get_blob_client(container=container, blob=blob)

    @classmethod
    def from_anything(cls, source) -> "AzureConnection":
        """Convenience: build an ``AzureConnection`` from a thing-or-spec.

        Accepts:
            - ``AzureConnection`` (returned as-is)
            - ``BlobServiceClient`` (wrapped without further resolution)
            - ``str`` (connection string)
            - ``dict`` (passed as kwargs)
            - ``None`` (defer to env / AAD)
        """
        if isinstance(source, cls):
            return source
        if isinstance(source, BlobServiceClient):
            inst = cls.__new__(cls)
            # Bypass dataclass init; pre-populate cached props.
            inst.credential = None
            inst.connection_string = None
            inst.account_url = None
            inst.account_key = None
            inst.client_kwargs = {}
            inst.__dict__["service_client"] = source
            return inst
        if isinstance(source, str):
            return cls(connection_string=source)
        if isinstance(source, dict):
            return cls(**source)
        if source is None:
            return cls()
        raise TypeError(
            f"Cannot build AzureConnection from {type(source).__name__}: {source!r}"
        )
