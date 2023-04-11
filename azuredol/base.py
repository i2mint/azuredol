"""Azure Storage Data Object Layer"""
from functools import cached_property
from azure.storage.blob import BlobServiceClient
from py2store import KvReader, KvPersister


class AzureBlobPersisterMixin(KvPersister):
    """Key-Value mapping for creating, updating, and deleting Azure storage blob data"""

    def __setitem__(self, k, v):
        """Create appendable blob and set value

        :param k: key
        :param v: blob data
        :return: None
        """
        blob_client = self.container_client.get_blob_client(blob=k)
        blob_client.create_append_blob()
        blob_client.append_block(v, length=len(v))

    def append(self, k, v):
        """Append to existing block

        :param k: key
        :param v: blob data
        :return: None
        """
        blob_client = self.container_client.get_blob_client(blob=k)
        blob_client.append_block(v, length=len(v))

    def __delitem__(self, k):
        """Delete blob

        :param k: key
        :return: None
        """
        blob_client = self.container_client.get_blob_client(blob=k)
        blob_client.delete_blob()


class AzureBlobReaderMixin(KvReader):
    """Key-Value mapping for accessing and reading Azure storage blob data"""

    @cached_property
    def container_client(self):
        return self.client.get_container_client(self.container_name)

    def __getitem__(self, k):
        """Download and return blob data

        :param k: key
        :return: blob data
        """
        blob_client = self.container_client.get_blob_client(blob=k)
        blob_data = blob_client.download_blob().readall()
        return blob_data

    def __iter__(self):
        """Iterate blob keys

        :return: Generator of blob keys
        """
        blob_iter = self.container_client.list_blobs()
        return (blob.name for blob in blob_iter)


class AzureBlobStore(AzureBlobReaderMixin, AzureBlobPersisterMixin):
    """Azure storage blob data key-value mapping for creating, reading, updating, and deleting"""

    def __init__(self, container_name: str, connection_string: str):
        """Connect to Azure storate blob service client to create and access appendable blob data

        :param container_name: unique identifier used to distinguish container instances
        :param connection_string: authorization info to access data in an Azure Storage account
        """
        self.container_name = container_name
        self.connection_string = connection_string
        self.client = BlobServiceClient.from_connection_string(connection_string)
