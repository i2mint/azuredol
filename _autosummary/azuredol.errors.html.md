# azuredol.errors

Custom exceptions and error-translation decorator for azuredol.

All Azure SDK exception handling for the Mapping-shaped methods on close-to-metal stores
funnels through `translate_azure_errors` so the auth-error vs not-found distinction
stays auditable from one place. See `misc/docs/design_decisions.md` §4.

### Functions

| [`translate_azure_errors`](#azuredol.errors.translate_azure_errors)(\*[, key_arg, ...])   | Decorator: translate Azure SDK exceptions into `KeyError` subclasses.   |
|-----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|

### Exceptions

| [`BlobAlreadyExistsError`](#azuredol.errors.BlobAlreadyExistsError)      | Raised on strict-create write attempts when the blob already exists.   |
|------------------------------------------------------------------------------|------------------------------------------------------------------------|
| [`BlobNotFoundError`](#azuredol.errors.BlobNotFoundError)           | Raised when a blob does not exist.                                     |
| [`ContainerAlreadyExistsError`](#azuredol.errors.ContainerAlreadyExistsError) | Raised on strict-create attempts when the container already exists.    |
| [`ContainerNotEmptyError`](#azuredol.errors.ContainerNotEmptyError)      | Raised on `del account_store[name]` when the container has blobs.      |
| [`ContainerNotFoundError`](#azuredol.errors.ContainerNotFoundError)      | Raised when a container does not exist.                                |

### *exception* azuredol.errors.BlobAlreadyExistsError

Bases: [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)

Raised on strict-create write attempts when the blob already exists.

`KeyError` subclass for symmetry with `BlobNotFoundError` — both signal a
key-vs-store mismatch.

### *exception* azuredol.errors.BlobNotFoundError

Bases: [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)

Raised when a blob does not exist. `KeyError` subclass so `Mapping` consumers work.

### *exception* azuredol.errors.ContainerAlreadyExistsError

Bases: [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)

Raised on strict-create attempts when the container already exists.

### *exception* azuredol.errors.ContainerNotEmptyError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised on `del account_store[name]` when the container has blobs.

The user must call `azuredol.delete_container(account_store, name, force=True)` to acknowledge the
cascading delete. See `misc/docs/design_decisions.md` §12.

### *exception* azuredol.errors.ContainerNotFoundError

Bases: [`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)

Raised when a container does not exist.

### azuredol.errors.translate_azure_errors(\*, key_arg=0, not_found_cls=<class 'azuredol.errors.BlobNotFoundError'>, exists_cls=<class 'azuredol.errors.BlobAlreadyExistsError'>)

Decorator: translate Azure SDK exceptions into `KeyError` subclasses.

Auth errors (`ClientAuthenticationError`) and all other Azure errors propagate
untouched — they are *never* swallowed as “key absent”. See
`misc/docs/design_decisions.md` §4.

* **Parameters:**
  * **key_arg** ([`int`](https://docs.python.org/3/builtins/functions.html#int) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Position (int) or name (str) of the key argument in the wrapped
    method’s signature. Used to populate `KeyError(key)`. The receiver
    `self` is at index 0, so the user-facing key is typically at index 1
    (the default).
  * **not_found_cls** ([`type`](https://docs.python.org/3/builtins/functions.html#type)[[`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)]) – Exception class to raise on `ResourceNotFoundError`.
  * **exists_cls** ([`type`](https://docs.python.org/3/builtins/functions.html#type)[[`KeyError`](https://docs.python.org/3/builtins/exceptions.html#KeyError)]) – Exception class to raise on `ResourceExistsError`.
* **Return type:**
  [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)
