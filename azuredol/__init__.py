"""Access Azure Storage through a mapping interface"""

from azuredol.base import (
    AzureFiles,
    AzureReader,
    AzureTextFiles,
)

from azuredol.functions import azure_func_service

from azuredol._old_base import AzureBlobStore  # deprecated
