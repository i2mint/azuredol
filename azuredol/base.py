"""Azure Storage Data Object Layer"""
from functools import cached_property
from azure.storage.blob import BlobServiceClient
from py2store import KvReader, KvPersister


class AzureBlobPersisterMixin(KvPersister):
    def __setitem__(self, k, v):
        blob_client = self.container_client.get_blob_client(blob=k)
        blob_client.create_append_blob()
        blob_client.append_block(v, length=len(v))

    def append(self, k, v):
        blob_client = self.container_client.get_blob_client(blob=k)
        blob_client.append_block(v, length=len(v))

    def __delitem__(self, k):
        blob_client = self.container_client.get_blob_client(blob=k)
        blob_client.delete_blob()


class AzureBlobReaderMixin(KvReader):
    @cached_property
    def container_client(self):
        return self.client.get_container_client(self.container_name)

    def __getitem__(self, k):
        blob_client = self.container_client.get_blob_client(blob=k)
        blob_data = blob_client.download_blob().readall()
        return blob_data

    def __iter__(self):
        blob_iter = self.container_client.list_blobs()
        return (blob.name for blob in blob_iter)


class AzureBlobStore(AzureBlobReaderMixin, AzureBlobPersisterMixin, object):
    def __init__(self, container_name: str, connection_string: str):
        self.container_name = container_name
        self.connection_string = connection_string
        self.client = BlobServiceClient.from_connection_string(connection_string)
