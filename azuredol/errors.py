"""Custom exceptions and error-translation decorator for azuredol.

All Azure SDK exception handling for the Mapping-shaped methods on close-to-metal stores
funnels through `translate_azure_errors` so the auth-error vs not-found distinction
stays auditable from one place. See ``misc/docs/design_decisions.md`` §4.
"""

from __future__ import annotations

import inspect
from functools import wraps
from typing import Callable

from azure.core.exceptions import (
    ResourceNotFoundError,
    ResourceExistsError,
)


def _extract_key(func, args, kwargs, key_arg):
    """Resolve the user-facing key from *args/**kwargs.

    Supports either a positional int index OR a name (resolved via the function's
    signature so it works whether the caller passed by position or by keyword).
    """
    if isinstance(key_arg, int):
        return args[key_arg] if key_arg < len(args) else None
    if key_arg in kwargs:
        return kwargs[key_arg]
    try:
        sig = inspect.signature(func)
        params = list(sig.parameters)
        idx = params.index(key_arg)
        return args[idx] if idx < len(args) else None
    except (ValueError, TypeError):
        return None


class BlobNotFoundError(KeyError):
    """Raised when a blob does not exist. ``KeyError`` subclass so ``Mapping`` consumers work."""


class BlobAlreadyExistsError(KeyError):
    """Raised on strict-create write attempts when the blob already exists.

    ``KeyError`` subclass for symmetry with ``BlobNotFoundError`` — both signal a
    key-vs-store mismatch.
    """


class ContainerNotFoundError(KeyError):
    """Raised when a container does not exist."""


class ContainerAlreadyExistsError(KeyError):
    """Raised on strict-create attempts when the container already exists."""


class ContainerNotEmptyError(RuntimeError):
    """Raised on ``del account_store[name]`` when the container has blobs.

    The user must call ``account_store.delete(name, force=True)`` to acknowledge the
    cascading delete. See ``misc/docs/design_decisions.md`` §12.
    """


def translate_azure_errors(
    *,
    key_arg: int | str = 0,
    not_found_cls: type[KeyError] = BlobNotFoundError,
    exists_cls: type[KeyError] = BlobAlreadyExistsError,
) -> Callable:
    """Decorator: translate Azure SDK exceptions into ``KeyError`` subclasses.

    Auth errors (``ClientAuthenticationError``) and all other Azure errors propagate
    untouched — they are *never* swallowed as "key absent". See
    ``misc/docs/design_decisions.md`` §4.

    Args:
        key_arg: Position (int) or name (str) of the key argument in the wrapped
            method's signature. Used to populate ``KeyError(key)``. The receiver
            ``self`` is at index 0, so the user-facing key is typically at index 1
            (the default).
        not_found_cls: Exception class to raise on ``ResourceNotFoundError``.
        exists_cls: Exception class to raise on ``ResourceExistsError``.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ResourceNotFoundError as e:
                k = _extract_key(func, args, kwargs, key_arg)
                raise not_found_cls(k) from e
            except ResourceExistsError as e:
                k = _extract_key(func, args, kwargs, key_arg)
                raise exists_cls(k) from e
            # Everything else (ClientAuthenticationError, HttpResponseError,
            # ServiceRequestError, ServiceResponseError, ...) propagates.

        return wrapper

    return decorator
