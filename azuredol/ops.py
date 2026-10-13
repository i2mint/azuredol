"""Key-taking and scope-wide operations, as free functions over the caller's (possibly wrapped) store.

``dol`` wraps stores by delegation, so a *method* of a wrapped azuredol store runs bound to
the inner leaf: it receives the caller's **outer**, unmapped key and reads the leaf's own
``prefix`` (i2mint/azuredol#4, i2mint/dol#83). Under a key codec that made
``AccountStore.delete('logs', force=True)`` cascade-delete the container literally named
``logs`` instead of ``tenantA-logs``, and ``ContainerCollection.walk`` list the wrong scope.
A free function is handed the outer store, so it resolves the key through every layer:

- :func:`delete_container` ``(store, name, force=False)``: ``del store[name]`` through the
  caller's store, with a context-scoped authorisation to cascade for that one container.
  Key mapping, read-only wrappers and scope checks (``name in store``) are the layers' own.
- :func:`walk` ``(store, delimiter)``: ``walk_blobs`` over the prefix the *caller's* empty
  key resolves to (leaf prefix + any key codec).

The removed methods (``AccountStore.delete``, ``ContainerCollection.walk``) now raise an
``AttributeError`` naming their replacement. This is the design of cosmodol.ops and s3dol's
ADR-0011.

What stays outside reach, stated rather than hidden: :func:`walk` yields raw Azure nodes whose
``.name`` is an absolute blob id (azure's own objects), and a ``filt_iter`` scope that filters
by key cannot narrow a server-side walk. A layer that performs the delete in another thread
escapes the cascade authorisation (the delete is then refused as non-empty, never widened).
"""

from __future__ import annotations

from typing import Any, Iterator

from dol import inner_most_key

from azuredol.base import (
    AccountStore,
    ContainerCollection,
    _CASCADE_ID,
)
from azuredol.errors import ContainerNotFoundError


def _leaf_of(store, cls):
    """The innermost layer of ``store`` that is an instance of ``cls``."""
    cur, seen = store, set()
    while not isinstance(cur, cls):
        inner = getattr(cur, "store", None)
        if inner is None or id(cur) in seen:
            raise TypeError(f"{type(store).__name__} does not wrap a {cls.__name__}")
        seen.add(id(cur))
        cur = inner
    return cur


def _inner_key(store, k):
    """``k`` resolved through every layer of ``store``; ``k`` itself if no layer maps keys."""
    inner = inner_most_key(store, k, default=None)
    return inner if isinstance(inner, str) else k


def delete_container(store, name: str, *, force: bool = False) -> None:
    """Delete container ``name`` (a key of ``store``); with ``force=True`` cascade-delete its blobs.

    The deletion is ``del store[name]`` on the caller's own store, so a key codec maps
    ``name``, a read-only wrapper refuses, and a scoped view cannot reach out of scope.

    :raises ContainerNotFoundError: if ``name`` is not a container of ``store``
    :raises ContainerNotEmptyError: if the container has blobs and ``force`` is false
    """
    _leaf_of(store, AccountStore)  # fail early if this is not an account store
    if name not in store:  # one point read through the outer store: scope + key mapping
        raise ContainerNotFoundError(name)
    token = _CASCADE_ID.set(_inner_key(store, name) if force else None)
    try:
        del store[name]
    finally:
        _CASCADE_ID.reset(token)


def walk(store, delimiter: str = "/") -> Iterator[Any]:
    """Hierarchical walk (``BlobProperties`` / ``BlobPrefix`` nodes) of ``store``'s own scope.

    The scope is the blob prefix the caller's empty key resolves to, so a key codec's prefix
    is included (unlike ``ContainerCollection.walk_ids``, which sees only the leaf's prefix).
    """
    leaf = _leaf_of(store, ContainerCollection)
    return leaf._container_client.walk_blobs(
        name_starts_with=_inner_key(store, ""), delimiter=delimiter
    )
