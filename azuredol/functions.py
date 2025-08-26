"""Azure functions tools"""

import subprocess
import threading
import time
import re
import contextlib
import sys
import shlex


@contextlib.contextmanager
def azure_func_service(
    rootfolder,
    extra_args='',
    *,
    verbose=True,
    wait_for_log=None,
    timeout=30,
    print_output=True,
):
    """
    Context manager to start an Azure Function host using `func start` in the specified folder.

    Parameters:
        rootfolder (str): The directory containing the Azure Function App.
        extra_args (str): Additional command-line arguments for the `func start` command.
        wait_for_log (str): A substring or regular expression pattern that indicates when the service is ready.
                          If provided, the context manager waits until a matching log line is detected.
        timeout (int): Maximum time in seconds to wait for the ready log message.
        print_output (bool): If True, prints the process output to stdout.

    Yields:
        subprocess.Popen: The process object representing the running Azure Functions host.

    Usage Example:
        with azure_func_service('/path/to/azure_func', extra_args="--verbose", wait_for_log=r'Host started') as proc:
            # Place code here to test the HTTP service.
            ...
    """
    # Construct the command to start the function host.
    cmd = ['func', 'start']
    if extra_args:
        cmd.extend(shlex.split(extra_args))

    # Launch the process in the given root folder.
    # Redirect stdout and stderr to allow monitoring of process output.
    if verbose:
        print(f"Starting Azure Function service in '{rootfolder}'...")

    proc = subprocess.Popen(
        cmd,
        cwd=rootfolder,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,  # Ensures the output is handled as text.
        bufsize=1,  # Line-buffered output.
    )

    # Event to signal that the required log output has been seen.
    ready_event = threading.Event()
    output_lines = []

    def reader():
        """
        Reads lines from the process output, prints them if requested,
        stores them in a list, and signals when a line matches the wait_for_log pattern.
        """
        for line in proc.stdout:
            if print_output:
                sys.stdout.write(line)
            output_lines.append(line)
            if wait_for_log and re.search(wait_for_log, line):
                ready_event.set()

    # Start a daemon thread to read the process output asynchronously.
    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    # If a waiting pattern is specified, poll for its occurrence.
    start_time = time.time()
    if wait_for_log:
        while not ready_event.is_set():
            if time.time() - start_time > timeout:
                proc.terminate()
                raise TimeoutError(
                    f"Timeout waiting for log pattern '{wait_for_log}'. Process output:\n{''.join(output_lines)}"
                )
            time.sleep(0.1)
    else:
        # Allow a brief pause for the process to initialize.
        time.sleep(1)

    try:
        yield proc
    finally:
        # Ensure that the process is terminated when the context is exited.
        proc.terminate()
        proc.wait()
        if verbose:
            print('Azure Function service stopped.')
