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

- :func:`substore` ``(store, key)``: the sub-store ``store['2026/']`` is meant to be, built
  through the caller's own store (i2mint/azuredol#6): ``substore(store, 'a/')[k]`` is always
  ``store['a/' + k]``, whatever wrappers (key or value codecs, scopes) sit on ``store``.

The removed methods (``AccountStore.delete``, ``ContainerCollection.walk``) now raise an
``AttributeError`` naming their replacement. This is the design of cosmodol.ops and s3dol's
ADR-0011.

What stays outside reach, stated rather than hidden: :func:`walk` yields raw Azure nodes whose
``.name`` is an absolute blob id (azure's own objects), and a ``filt_iter`` scope that filters
by key cannot narrow a server-side walk. A layer that performs the delete in another thread
escapes the cascade authorisation (the delete is then refused as non-empty, never widened).
"""

from __future__ import annotations

import inspect
from typing import Any, Iterator

from dol import KeyCodecs, inner_most_key

from azuredol.base import (
    AccountStore,
    ContainerCollection,
    ContainerReader,
    _CASCADE_ID,
)
from azuredol.errors import ContainerNotFoundError


def _leaf_of(store, cls):
    """The innermost layer of ``store`` that is an instance of ``cls``.

    Every wrapper layer above it must define ``_id_of_key`` (dol's ``Store`` layers do): a
    layer that maps keys without it cannot be resolved by ``inner_most_key``, which would then
    hand back an unmapped key and act on the wrong blob/container, so it is refused
    (``TypeError``; i2mint/azuredol#7).
    """
    cur, seen = store, set()
    while not isinstance(cur, cls):
        if not callable(inspect.getattr_static(cur, "_id_of_key", None)):  # not via __getattr__
            raise TypeError(
                f"{type(cur).__name__} wraps a {cls.__name__} but defines no _id_of_key, so "
                "keys cannot be resolved through it; build wrappers with dol (Store, "
                "wrap_kvs, KeyCodecs, ...)."
            )
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
    leaf = _leaf_of(store, AccountStore)  # fail early if this is not an account store
    if name not in store:  # one point read through the outer store: scope + key mapping
        raise ContainerNotFoundError(name)
    token = _CASCADE_ID.set((id(leaf), _inner_key(store, name)) if force else None)
    try:
        del store[name]
    finally:
        _CASCADE_ID.reset(token)


def walk(store, delimiter: str = "/") -> Iterator[Any]:
    """Hierarchical walk (``BlobProperties`` / ``BlobPrefix`` nodes) of ``store``'s own scope.

    The scope is the blob prefix the caller's empty key resolves to, so a key codec's prefix
    is included (a codec that is not a pure prefix, e.g. a suffix, raises ``ValueError``; unlike ``ContainerCollection.walk_ids``, which sees only the leaf's prefix).
    """
    leaf = _leaf_of(store, ContainerCollection)
    scope = _inner_key(store, "")
    if _inner_key(store, "probe") != scope + "probe":
        raise ValueError(
            "walk needs a store whose key codec only adds a prefix: this one maps the empty "
            f"key to {scope!r} but 'probe' to {_inner_key(store, 'probe')!r}. Use "
            "walk_ids() on the leaf, or iterate the store."
        )
    return leaf._container_client.walk_blobs(
        name_starts_with=scope, delimiter=delimiter
    )


def substore(store, key: str):
    """The sub-store of ``store`` under ``key`` (a key ending in ``'/'``), as the caller sees it.

    ``substore(store, 'a/')[k]`` is ``store['a/' + k]`` for every wrapper stack on ``store``.
    On a bare ``ContainerStore`` it is the cheap, server-scoped ``store['a/']`` (listing only
    ``a/``'s blobs). On anything wrapped (a ``dol`` key/value codec or scope, including the
    classes ``typed_store``/``AzureJsonStore`` build) it is a ``KeyCodecs.prefixed(key)`` view
    *of that store*, so the caller's key and value mappings still apply; that view lists the
    wrapped store's whole scope and keeps the keys under ``key``. (``store['a/']`` on a store
    wrapped as an instance is minted by the innermost class and does not know about the
    wrappers: i2mint/azuredol#6.)

    :param store: a ``ContainerReader``/``ContainerStore``, wrapped or not
    :param key: a non-empty key ending in ``'/'``
    """
    if not isinstance(key, str) or not key.endswith("/") or key == "/":
        raise ValueError(f"A sub-store key must be a non-empty str ending in '/': {key!r}")
    leaf = _leaf_of(store, ContainerReader)
    if store is leaf:
        return leaf._with(prefix=leaf._id_of_key(key))
    return KeyCodecs.prefixed(key)(store)
