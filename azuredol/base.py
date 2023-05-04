"""Azure Storage Data Object Layer"""
from dataclasses import dataclass
from azure.storage.blob import ContainerClient
from dol import KvReader, KvPersister

AZURE_STORAGE_BLOCK_SIZE_LIMIT = 4 * 1024 * 1024  # 4MB


class AzureBlobPersisterMixin(KvPersister):
    """Key-Value mapping for creating, updating, and deleting Azure storage blob data"""

    def __setitem__(self, k, v):
        """Create appendable blob and set value

        :param k: key
        :param v: blob data
        :return: None
        """
        blob_client = self._container_client.get_blob_client(blob=self._id_of_key(k))
        blob_client.create_append_blob()
        if v:
            v_bytes = v.encode() if isinstance(v, str) else bytes(v)
            for i in range(0, len(v_bytes), AZURE_STORAGE_BLOCK_SIZE_LIMIT):
                blob_client.append_block(
                    v_bytes[i : i + AZURE_STORAGE_BLOCK_SIZE_LIMIT]
                )

    # TODO: Would be nice to have store[k].append(v) instead of this. The hard part is
    # that we don't want to download the blob when calling store[k] in this case.
    def append_to_value(self, k, v):
        """Append to existing block

        :param k: key
        :param v: blob data
        :return: None
        """
        blob_client = self._container_client.get_blob_client(blob=self._id_of_key(k))
        blob_client.append_block(v, length=len(v))

    def __delitem__(self, k):
        """Delete blob

        :param k: key
        :return: None
        """
        blob_client = self._container_client.get_blob_client(blob=self._id_of_key(k))
        blob_client.delete_blob()


class AzureBlobReaderMixin(KvReader):
    """Key-Value mapping for accessing and reading Azure storage blob data"""

    def __getitem__(self, k):
        """Download and return blob data

        :param k: key
        :return: blob data
        """
        blob_client = self._container_client.get_blob_client(blob=self._id_of_key(k))
        blob_data = blob_client.download_blob().readall()
        return blob_data

    def __iter__(self):
        """Iterate blob keys

        :return: Generator of blob keys
        """
        blob_iter = self._container_client.list_blobs(self.path)
        return (self._key_of_id(blob.name) for blob in blob_iter)


@dataclass
class AzureBlobStore(AzureBlobReaderMixin, AzureBlobPersisterMixin):
    """Azure storage blob data key-value mapping for creating, reading, updating, and 
    deleting

    :param container_name: unique identifier used to distinguish container instances
    :param connection_string: authorization info to access data in an Azure Storage 
    account

    Let's use the local Azure Storage Emulator to test this out. Make sure you have the 
    emulator installed and running.

    >>> connection_string='DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;'
    >>> container_name='azuredol-container'

    We create a store instance with a path as a prefix to all keys:

    >>> store = AzureBlobStore(connection_string, container_name, path='some/path')

    We can create a blob and set its value:

    >>> store['k1'] = 'v1'
    >>> store['k1']
    b'v1'

    We can append to the blob's value:

    >>> store.append_to_value('k1', 'v1')
    >>> store['k1']
    b'v1v1'

    Let's create another blob:

    >>> store['k2'] = 'v2'
    >>> store['k2']
    b'v2'

    We can list the keys of the store:

    >>> list(store)
    ['k1', 'k2']

    We can list the values of the store:

    >>> list(store.values())
    [b'v1v1', b'v2']

    We can list the items of the store:

    >>> list(store.items())
    [('k1', b'v1v1'), ('k2', b'v2')]

    Let's create another store instance without a path. We can see that the key is 
    present in this store as well:

    >>> store_all = AzureBlobStore(connection_string, container_name)
    >>> list(store_all)
    ['some/path/k1', 'some/path/k2']

    We can delete a blob:

    >>> del store['k1']

    We can see that the blob is deleted from the stores:

    >>> list(store)
    ['k2']
    >>> list(store_all)
    ['some/path/k2']

    We can create another store instance with a different path and add a blob. We can 
    see that the blob is present in this store but not the first one. Also, the blob is 
    present in the store without a path:

    >>> other_store = AzureBlobStore(connection_string, container_name, path='some/other/path')
    >>> other_store['k1'] = 'v1'
    >>> list(other_store)
    ['k1']
    >>> list(store)
    ['k2']
    >>> list(store_all)
    ['some/other/path/k1', 'some/path/k2']

    But, we can create a last store with a path that is the common prefix of the other 
    two paths. And we can see that both blobs are present in this store:

    >>> a_last_store = AzureBlobStore(connection_string, container_name, path='some')
    >>> list(a_last_store)
    ['other/path/k1', 'path/k2']

    Let's delete all the blobs, to keep the Azure Storage Emulator clean:
    
    >>> for k in store_all:
    ...     del store_all[k]
    
    """

    connection_string: str
    container_name: str
    create_container_if_missing: bool = True
    path: str = None

    def __post_init__(self):
        """Connect to Azure storate blob service client to create and access appendable 
        blob data"""
        self._container_client = ContainerClient.from_connection_string(
            self.connection_string, self.container_name
        )
        if not self._container_client.exists():
            if self.create_container_if_missing:
                self._container_client.create_container()
            else:
                raise ValueError(f'Container {self.container_name} does not exist')
        self.path = f"{self.path.strip('/')}/" if self.path else ''

    def _id_of_key(self, k):
        return f'{self.path}{k}'

    def _key_of_id(self, id):
        return id[len(self.path) :]
