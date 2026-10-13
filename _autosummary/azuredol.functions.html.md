# azuredol.functions

Azure functions tools

### Functions

| [`azure_func_service`](#azuredol.functions.azure_func_service)(rootfolder[, extra_args, ...])   | Context manager to start an Azure Function host using `func start` in the specified folder.   |
|------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|

### azuredol.functions.azure_func_service(rootfolder, extra_args='', , verbose=True, wait_for_log=None, timeout=30, print_output=True)

Context manager to start an Azure Function host using `func start` in the specified folder.

* **Parameters:**
  * **rootfolder** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – The directory containing the Azure Function App.
  * **extra_args** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – Additional command-line arguments for the `func start` command.
  * **wait_for_log** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – A substring or regular expression pattern that indicates when the service is ready.
    If provided, the context manager waits until a matching log line is detected.
  * **timeout** ([*int*](https://docs.python.org/3/builtins/functions.html#int)) – Maximum time in seconds to wait for the ready log message.
  * **print_output** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool)) – If True, prints the process output to stdout.
* **Yields:**
  *subprocess.Popen* – The process object representing the running Azure Functions host.

Usage Example:
: with azure_func_service(‘/path/to/azure_func’, extra_args=”–verbose”, wait_for_log=r’Host started’) as proc:
  : # Place code here to test the HTTP service.
    …
