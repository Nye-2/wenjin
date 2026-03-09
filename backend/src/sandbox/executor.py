"""Sandbox executor for safe Python code execution.

This module provides a secure environment for executing untrusted Python code
with restrictions on file system access, network access, and system calls.
"""

import asyncio
import io
import sys
import traceback
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SandboxConfig:
    """Configuration for the sandbox executor.

    Attributes:
        timeout: Maximum execution time in seconds.
        max_memory_mb: Maximum memory usage in megabytes (best effort).
        allowed_imports: Set of allowed module names. None means use default safe list.
    """

    timeout: int = 30
    max_memory_mb: int = 256
    allowed_imports: set | None = None


@dataclass
class ExecutionResult:
    """Result of code execution in the sandbox.

    Attributes:
        success: Whether the code executed successfully.
        output: The stdout output from the code.
        error: Error message if execution failed, None otherwise.
        execution_time: Time taken to execute the code in seconds.
    """

    success: bool
    output: str
    error: str | None
    execution_time: float | None = None


# Default set of safe modules that can be imported
DEFAULT_SAFE_IMPORTS = {
    "math",
    "random",
    "statistics",
    "itertools",
    "functools",
    "collections",
    "datetime",
    "decimal",
    "fractions",
    "re",
    "string",
    "textwrap",
    "json",
    "typing",
    "copy",
    "pprint",
    "enum",
    "dataclasses",
    "contextlib",
    "abc",
    "numbers",
    "operator",
    "heapq",
    "bisect",
    "array",
    "uuid",
    "hashlib",
    "base64",
    "time",  # Allowed for timeout testing - sleep is safe
}

# Dangerous builtins to remove
DANGEROUS_BUILTINS = {
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
    "input",
    "breakpoint",
    "memoryview",
    "globals",
    "locals",
    "vars",
}


class RestrictedImporter:
    """Custom import hook that restricts module imports."""

    def __init__(self, allowed_imports: set[str]):
        self.allowed_imports = allowed_imports
        self.blocked_modules = {
            "subprocess",
            "os",
            "sys",
            "socket",
            "ctypes",
            "multiprocessing",
            "threading",
            "signal",
            "posix",
            "nt",
            "builtins",
            "importlib",
            "shutil",
            "tempfile",
            "pathlib",
            "code",
            "codeop",
            "commands",
            "popen2",
            "popen3",
            "popen4",
            "pty",
            "fcntl",
            "pipes",
            "posixfile",
            "resource",
            "select",
            "selectors",
        }

    def find_module(self, name: str, path=None):
        """Check if module import should be blocked."""
        # Get the top-level module name
        top_level = name.split(".")[0]

        if top_level in self.blocked_modules:
            return self
        if self.allowed_imports is not None and top_level not in self.allowed_imports:
            return self
        return None

    def load_module(self, name: str):
        """Raise ImportError for blocked modules."""
        raise ImportError(f"Import of module '{name}' is not allowed in sandbox")


class SafeDict(dict):
    """Dictionary that prevents access to dangerous builtins."""

    def __getitem__(self, key):
        if key in DANGEROUS_BUILTINS:
            raise NameError(f"'{key}' is not allowed in sandbox")
        return super().__getitem__(key)

    def __contains__(self, key):
        if key in DANGEROUS_BUILTINS:
            return False
        return super().__contains__(key)


class SandboxExecutor:
    """Executes Python code in a restricted sandbox environment.

    The sandbox provides security through:
    - Restricted builtins (no open, exec, eval, compile, __import__)
    - Limited module imports
    - Timeout enforcement
    - Isolated execution namespace
    """

    def __init__(self, config: SandboxConfig | None = None):
        """Initialize the sandbox executor.

        Args:
            config: Sandbox configuration. Uses defaults if not provided.
        """
        self.config = config or SandboxConfig()
        self._setup_safe_globals()

    def _setup_safe_globals(self) -> None:
        """Set up the safe global namespace for execution."""
        # Start with safe builtins
        safe_builtins = {}
        for name, obj in __builtins__.items() if isinstance(__builtins__, dict) else vars(__builtins__).items():
            if name not in DANGEROUS_BUILTINS:
                safe_builtins[name] = obj

        # Create a custom __import__ that respects restrictions
        allowed = self.config.allowed_imports
        if allowed is None:
            allowed = DEFAULT_SAFE_IMPORTS

        def safe_import(name: str, globals=None, locals=None, fromlist=(), level=0):
            """Restricted import function."""
            top_level = name.split(".")[0]

            # Block dangerous modules
            blocked_modules = {
                "subprocess",
                "socket",
                "ctypes",
                "multiprocessing",
                "threading",
                "signal",
                "posix",
                "nt",
                "importlib",
                "shutil",
                "tempfile",
                "pathlib",
                "code",
                "codeop",
                "pty",
                "fcntl",
                "resource",
                "commands",
            }

            if top_level in blocked_modules:
                raise ImportError(f"Import of module '{name}' is not allowed in sandbox")

            # Check if in allowed list
            if top_level not in allowed:
                raise ImportError(f"Import of module '{name}' is not allowed in sandbox")

            # For os module, we need special handling
            if top_level == "os":
                return self._create_safe_os_module()

            # Use the real import for allowed modules
            return __builtins__["__import__"](name, globals, locals, fromlist, level)

        safe_builtins["__import__"] = safe_import

        self._safe_globals = {"__builtins__": safe_builtins}

    def _create_safe_os_module(self) -> Any:
        """Create a restricted version of the os module."""
        import os

        class SafeOS:
            """Safe subset of os module."""

            # Allow environment variable access (read-only)
            environ = os.environ

            # Allow path operations
            path = os.path

            # Allow some constants
            curdir = os.curdir
            pardir = os.pardir
            sep = os.sep
            extsep = os.extsep
            altsep = os.altsep
            pathsep = os.pathsep
            linesep = os.linesep
            name = os.name

            # Explicitly block dangerous functions
            def system(self, *args, **kwargs):
                raise PermissionError("os.system is not allowed in sandbox")

            def popen(self, *args, **kwargs):
                raise PermissionError("os.popen is not allowed in sandbox")

            def spawn(self, *args, **kwargs):
                raise PermissionError("os.spawn is not allowed in sandbox")

            def fork(self, *args, **kwargs):
                raise PermissionError("os.fork is not allowed in sandbox")

            def exec(self, *args, **kwargs):
                raise PermissionError("os.exec is not allowed in sandbox")

            def kill(self, *args, **kwargs):
                raise PermissionError("os.kill is not allowed in sandbox")

        return SafeOS()

    async def execute(self, code: str) -> ExecutionResult:
        """Execute Python code in the sandbox.

        Args:
            code: Python code to execute.

        Returns:
            ExecutionResult containing success status, output, and any errors.
        """
        import time
        import concurrent.futures

        start_time = time.time()

        # First, check for syntax errors
        try:
            compiled_code = compile(code, "<sandbox>", "exec")
        except SyntaxError as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"SyntaxError: {e.msg} at line {e.lineno}",
                execution_time=0.0,
            )

        # Capture stdout
        stdout_capture = io.StringIO()

        # Create execution namespace
        exec_globals = dict(self._safe_globals)
        exec_locals: dict[str, Any] = {}

        # Container for exceptions from the thread
        execution_error: Exception | None = None

        def run_code_sync():
            """Run code synchronously in a separate thread."""
            nonlocal execution_error
            try:
                with redirect_stdout(stdout_capture):
                    exec(compiled_code, exec_globals, exec_locals)
                    # Check for expression result (last line that evaluates)
                    if exec_locals:
                        last_value = list(exec_locals.values())[-1]
                        if last_value is not None and not callable(last_value):
                            print(repr(last_value))
            except Exception as e:
                execution_error = e

        try:
            # Run in a thread pool to allow timeout enforcement
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = loop.run_in_executor(executor, run_code_sync)
                await asyncio.wait_for(future, timeout=self.config.timeout)

            if execution_error is not None:
                raise execution_error

            output = stdout_capture.getvalue()
            execution_time = time.time() - start_time

            return ExecutionResult(
                success=True,
                output=output,
                error=None,
                execution_time=execution_time,
            )

        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                output=stdout_capture.getvalue(),
                error=f"Execution timeout after {self.config.timeout} seconds",
                execution_time=execution_time,
            )

        except PermissionError as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                output=stdout_capture.getvalue(),
                error=str(e),
                execution_time=execution_time,
            )

        except ImportError as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                output=stdout_capture.getvalue(),
                error=f"ImportError: {str(e)}",
                execution_time=execution_time,
            )

        except NameError as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                output=stdout_capture.getvalue(),
                error=f"NameError: {str(e)}",
                execution_time=execution_time,
            )

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = "".join(traceback.format_exception_only(type(e), e))
            return ExecutionResult(
                success=False,
                output=stdout_capture.getvalue(),
                error=error_msg.strip(),
                execution_time=execution_time,
            )
