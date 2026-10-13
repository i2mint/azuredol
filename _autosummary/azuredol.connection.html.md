# azuredol.connection

Connection-layer for azuredol.

Owns the expensive resource (`BlobServiceClient`) and the credential cascade.
See `misc/docs/architecture.md` Layer A and `misc/docs/design_decisions.md` §6.

### Module Attributes

| [`CredentialLike`](#azuredol.connection.CredentialLike)   | account-key string, connection string, SAS string, dict of kwargs, `azure.identity` credential object, or None (defer to env / DefaultAzureCredential).   |
|-------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|

### Functions

| [`resolve_credential`](#azuredol.connection.resolve_credential)(\*[, credential, ...])   | Resolve a credential into a normalized form that can build a `BlobServiceClient`.   |
|----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|

### Classes

| [`AzureConnection`](#azuredol.connection.AzureConnection)([credential, ...])   | Holds a resolved credential and a lazy `BlobServiceClient`.   |
|---------------------------------------------------------------------------------------|---------------------------------------------------------------|

### *class* azuredol.connection.AzureConnection(credential=None, connection_string=None, account_url=None, account_key=None, client_kwargs=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Holds a resolved credential and a lazy `BlobServiceClient`.

This is the dependency-injection seam for the whole package. Tests construct one
pointing at Azurite without touching any store class.

* **Parameters:**
  * **credential** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`None`](https://docs.python.org/3/builtins/constants.html#None)]) – explicit credential object, key string, or SAS string.
  * **connection_string** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – full connection string (overrides `credential`).
  * **account_url** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – storage account URL (with or without credential).
  * **account_key** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – shared-key for the account.

All four args are optional; the credential cascade in
`resolve_credential` is consulted if none are provided.

#### blob_client(container, blob)

Cheap derivation of a `BlobClient` from the shared service client.

#### container_client(container)

Cheap derivation of a `ContainerClient` from the shared service client.

#### *classmethod* from_anything(source)

Convenience: build an `AzureConnection` from a thing-or-spec.

Accepts:

> - `AzureConnection` (returned as-is)
> - `BlobServiceClient` (wrapped without further resolution)
> - `str` (connection string)
> - `dict` (passed as kwargs)
> - `None` (defer to env / AAD)
* **Return type:**
  [`AzureConnection`](#azuredol.connection.AzureConnection)

#### *property* service_client *: BlobServiceClient*

The lazily-constructed `BlobServiceClient`. Cached for the connection’s lifetime.

### azuredol.connection.CredentialLike

account-key string, connection string, SAS string, dict of kwargs,
`azure.identity` credential object, or None (defer to env / DefaultAzureCredential).

* **Type:**
  Any of

alias of [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`Any`](https://docs.python.org/3/library/typing.html#typing.Any) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### azuredol.connection.resolve_credential(, credential=None, connection_string=None, account_url=None, account_key=None)

Resolve a credential into a normalized form that can build a `BlobServiceClient`.

Cascade (first hit wins):

1. Explicit `credential=`
2. Explicit `connection_string=`
3. Explicit `account_url=` + `account_key=` (or just `account_url=` + AAD)
4. Env var `AZURE_STORAGE_CONNECTION_STRING`
5. Env vars `AZURE_STORAGE_ACCOUNT_URL` + `AZURE_STORAGE_ACCOUNT_KEY`
6. Env var `AZURE_STORAGE_ACCOUNT_URL` alone + `DefaultAzureCredential`

* **Returns:**
  `{"conn_str": "..."}`                            # for from_connection_string
  `{"account_url": "...", "credential": <obj>}`    # for \_\_init_\_
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
* **Raises:**
  [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – if no source resolves.
