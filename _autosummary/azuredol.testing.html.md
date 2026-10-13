# azuredol.testing

Testing helpers for azuredol — Azurite fixture and convenience builders.

The Azurite-backed pieces require Docker to be available locally. Unit tests that don’t
need a live container should prototype with `dict()` per the dol convention.

### Functions

| [`azurite`](#azuredol.testing.azurite)([container_name, wait])         | Context manager that ensures Azurite is running for the duration.       |
|------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`azurite_is_running`](#azuredol.testing.azurite_is_running)()                    | Return True if Azurite's blob endpoint (port 10000) is reachable.       |
| [`docker_available`](#azuredol.testing.docker_available)()                      | Return True if the `docker` CLI is on PATH.                             |
| [`mk_test_store`](#azuredol.testing.mk_test_store)([container, prefix, ...]) | Build a `ContainerStore` pointing at Azurite, ready for ad-hoc testing. |
| [`pytest_azurite_connection`](#azuredol.testing.pytest_azurite_connection)()             | Importable as a pytest fixture body. Use it like::.                     |

### azuredol.testing.azurite(container_name=None, , wait=5.0)

Context manager that ensures Azurite is running for the duration.

If Azurite is already up (port 10000 reachable), do nothing on enter/exit.
Otherwise start it via `docker run` and stop it on exit.

* **Parameters:**
  * **container_name** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Docker container name. Random by default.
  * **wait** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Max seconds to wait for the blob port to come up.
* **Yields:**
  The Azurite connection string.
* **Raises:**
  [**RuntimeError**](https://docs.python.org/3/builtins/exceptions.html#RuntimeError) – if Docker is unavailable and Azurite is not already running.

### azuredol.testing.azurite_is_running()

Return True if Azurite’s blob endpoint (port 10000) is reachable.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### azuredol.testing.docker_available()

Return True if the `docker` CLI is on PATH.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### azuredol.testing.mk_test_store(container=None, , prefix='', create_container_if_missing=True)

Build a `ContainerStore` pointing at Azurite, ready for ad-hoc testing.

Requires Azurite to be running. Use the `azurite(...)` context manager to ensure it.

* **Parameters:**
  * **container** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Container name. Defaults to a random `azuredol-test-*` name.
  * **prefix** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Optional key prefix to scope the store.
  * **create_container_if_missing** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Create the container on first use.
* **Return type:**
  [`ContainerStore`](azuredol.base.html.md#azuredol.base.ContainerStore)

### azuredol.testing.pytest_azurite_connection()

Importable as a pytest fixture body. Use it like:

```default
import pytest
from azuredol.testing import pytest_azurite_connection

@pytest.fixture(scope='session')
def azurite_connection():
    yield from pytest_azurite_connection()
```

Skips the test session if Azurite cannot be started.
