"""Unit tests for azuredol error translation (no network)."""

import pytest
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceExistsError,
    ResourceNotFoundError,
)

from azuredol import (
    BlobAlreadyExistsError,
    BlobNotFoundError,
    translate_azure_errors,
)


def test_not_found_translates_to_blobnotfound():
    @translate_azure_errors(key_arg=0)
    def getter(k):
        raise ResourceNotFoundError(message="nope")

    with pytest.raises(KeyError) as ei:
        getter("k1")
    assert isinstance(ei.value, BlobNotFoundError)
    assert ei.value.args == ("k1",)


def test_exists_translates_to_blobexists():
    @translate_azure_errors(key_arg=0)
    def putter(k):
        raise ResourceExistsError(message="conflict")

    with pytest.raises(KeyError) as ei:
        putter("k1")
    assert isinstance(ei.value, BlobAlreadyExistsError)


def test_auth_error_never_swallowed():
    """ClientAuthenticationError must propagate untouched — never as KeyError."""

    @translate_azure_errors(key_arg=0)
    def getter(k):
        raise ClientAuthenticationError(message="bad credential")

    with pytest.raises(ClientAuthenticationError):
        getter("k1")


def test_http_error_propagates():
    @translate_azure_errors(key_arg=0)
    def f(k):
        raise HttpResponseError(message="server error")

    with pytest.raises(HttpResponseError):
        f("k1")


def test_key_arg_by_name():
    @translate_azure_errors(key_arg="blob")
    def f(blob):
        raise ResourceNotFoundError(message="nope")

    with pytest.raises(KeyError) as ei:
        f(blob="my_blob")
    assert ei.value.args == ("my_blob",)


def test_key_arg_by_name_resolves_positional():
    """Calling with positional should still find the right arg via the signature."""

    @translate_azure_errors(key_arg="blob")
    def f(self, blob, partition):
        raise ResourceNotFoundError(message="nope")

    with pytest.raises(KeyError) as ei:
        f("self_obj", "my_blob", "pk")
    assert ei.value.args == ("my_blob",)
