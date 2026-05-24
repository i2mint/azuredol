"""Testing helpers for azuredol — Azurite fixture and convenience builders.

The Azurite-backed pieces require Docker to be available locally. Unit tests that don't
need a live container should prototype with ``dict()`` per the dol convention.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import uuid
from contextlib import contextmanager
from typing import Optional

from azuredol.connection import AzureConnection
from azuredol.base import ContainerStore


# Azurite's well-known connection string. Same on every Azurite instance.
AZURITE_CONNECTION_STRING = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    "QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;"
    "TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;"
)

# SDK shorthand recognised by from_connection_string.
AZURITE_DEV_STORAGE = "UseDevelopmentStorage=true"


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def azurite_is_running() -> bool:
    """Return True if Azurite's blob endpoint (port 10000) is reachable."""
    return _port_open("127.0.0.1", 10000)


def docker_available() -> bool:
    """Return True if the ``docker`` CLI is on PATH."""
    return shutil.which("docker") is not None


@contextmanager
def azurite(container_name: Optional[str] = None, *, wait: float = 5.0):
    """Context manager that ensures Azurite is running for the duration.

    If Azurite is already up (port 10000 reachable), do nothing on enter/exit.
    Otherwise start it via ``docker run`` and stop it on exit.

    Args:
        container_name: Docker container name. Random by default.
        wait: Max seconds to wait for the blob port to come up.

    Yields:
        The Azurite connection string.

    Raises:
        RuntimeError: if Docker is unavailable and Azurite is not already running.
    """
    if azurite_is_running():
        yield AZURITE_CONNECTION_STRING
        return

    if not docker_available():
        raise RuntimeError(
            "Azurite is not running and Docker is not available. "
            "Start Azurite manually: "
            "`docker run -p 10000:10000 -p 10001:10001 -p 10002:10002 "
            "mcr.microsoft.com/azure-storage/azurite`"
        )

    container_name = container_name or f"azurite-test-{uuid.uuid4().hex[:8]}"
    cmd = [
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        container_name,
        "-p",
        "10000:10000",
        "-p",
        "10001:10001",
        "-p",
        "10002:10002",
        "mcr.microsoft.com/azure-storage/azurite",
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + wait
        while not azurite_is_running():
            if time.time() > deadline:
                raise RuntimeError(
                    f"Azurite did not start within {wait}s (port 10000 still closed)."
                )
            time.sleep(0.2)
        yield AZURITE_CONNECTION_STRING
    finally:
        subprocess.call(
            ["docker", "rm", "-f", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def mk_test_store(
    container: Optional[str] = None,
    *,
    prefix: str = "",
    create_container_if_missing: bool = True,
) -> ContainerStore:
    """Build a ``ContainerStore`` pointing at Azurite, ready for ad-hoc testing.

    Requires Azurite to be running. Use the ``azurite(...)`` context manager to ensure it.

    Args:
        container: Container name. Defaults to a random ``azuredol-test-*`` name.
        prefix: Optional key prefix to scope the store.
        create_container_if_missing: Create the container on first use.
    """
    container = container or f"azuredol-test-{uuid.uuid4().hex[:8]}"
    conn = AzureConnection(connection_string=AZURITE_CONNECTION_STRING)
    return ContainerStore(
        container,
        prefix=prefix,
        connection=conn,
        create_container_if_missing=create_container_if_missing,
    )


def pytest_azurite_connection():
    """Importable as a pytest fixture body. Use it like::

        import pytest
        from azuredol.testing import pytest_azurite_connection

        @pytest.fixture(scope='session')
        def azurite_connection():
            yield from pytest_azurite_connection()

    Skips the test session if Azurite cannot be started.
    """
    import pytest  # local import — pytest is a dev-only dep

    if azurite_is_running():
        yield AzureConnection(connection_string=AZURITE_CONNECTION_STRING)
        return

    if not docker_available():
        pytest.skip(
            "Azurite is not running and Docker is unavailable.", allow_module_level=True
        )

    with azurite() as conn_str:
        yield AzureConnection(connection_string=conn_str)
