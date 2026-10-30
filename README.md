# azuredol
Azure Storage Data Object Layer

To install:	```pip install azuredol```

## Sub-stores: use `substore()`

To get the part of a store under a prefix, prefer `azuredol.substore(store, 'sub/')`: it is the portable form and returns a sub-store through any wrapper stack on `store` (key codecs, value codecs, scopes), so `substore(store, 'sub/')[k]` is always `store['sub/' + k]`.

```python
from azuredol import substore

sub = substore(store, '2026/')
```

`store['sub/']` (a key ending in `/`) also works and is kept, but only on a bare store and on typed-store classes (`typed_store`, `AzureJsonStore`). It does not work through every wrapper stack: a dol wrapper placed on top of an *instance* is not carried into `store['sub/']`.
