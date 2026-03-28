"""Python AST sanitizer.

This module provides security validation for Python code using AST analysis
to prevent dangerous operations like system access, file manipulation, and
code execution.
"""

import ast

# Allowed modules for safe execution
# Note: Only use real module names, not import aliases (e.g., 'numpy' not 'np')
ALLOWED_MODULES: set[str] = {
    # Scientific computing
    'numpy',
    'scipy',
    'pandas',
    'sklearn',

    # Plotting and visualization
    'matplotlib',
    'matplotlib.pyplot',
    'seaborn',
    'plotly',
    'bokeh',

    # Data processing
    'json',
    'csv',
    'math',
    'statistics',
    'random',
    'datetime',
    'collections',
    'itertools',
    'functools',
    'typing',
    'dataclasses',
    'enum',
    'copy',
    're',
    'string',
    'textwrap',
    'uuid',
    'hashlib',
    'base64',
    'decimal',
    'fractions',

    # Image processing (safe subset)
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'PIL.ImageFilter',
    'cv2',

    # Safe I/O (memory only, no filesystem)
    'io',

    # Math/symbolic
    'sympy',
}

# Explicitly forbidden modules
FORBIDDEN_MODULES: set[str] = {
    'os',
    'sys',
    'subprocess',
    'shutil',
    'socket',
    'socketserver',
    'http.server',
    'http.client',
    'urllib',
    'urllib2',
    'urllib3',
    'requests',
    'ftplib',
    'smtplib',
    'telnetlib',
    'poplib',
    'imaplib',
    'nntplib',
    'popen2',
    'commands',
    'pty',
    'fcntl',
    'pipes',
    'posix',
    'posixpath',
    'signal',
    'ctypes',
    'multiprocessing',
    'threading',
    '_thread',
    'code',
    'codeop',
    'compile',
    'compileall',
    'pickle',
    'shelve',
    'marshal',
    'imp',
    'importlib',
    'pkgutil',
    'modulefinder',
    'zipimport',
    'ast',
    'dis',
    'inspect',
    'bdb',
    'pdb',
    'profile',
    'cProfile',
    'pstats',
    'timeit',
    'trace',
    'tracemalloc',
    'gc',
    'builtins',
    '__builtin__',
    'winreg',
    'winsound',
    'msvcrt',
    'glob',
    'tempfile',
    'secrets',
    'getpass',
    'termios',
    'tty',
    'resource',
    'syslog',
    'logging',
    'argparse',
    'optparse',
    'getopt',
    'asyncio',
    'concurrent',
    'concurrent.futures',
    'queue',
}

# Forbidden function names (builtins or commonly used dangerous functions)
FORBIDDEN_FUNCTIONS: set[str] = {
    'eval',
    'exec',
    'compile',
    '__import__',
    'open',
    'input',
    'breakpoint',
    'memoryview',
    'globals',
    'locals',
    'vars',
    'dir',
    'getattr',
    'setattr',
    'delattr',
    'hasattr',
    'type',
    'help',
    'license',
    'credits',
    'copyright',
    'quit',
    'exit',
}


class SecurityVisitor(ast.NodeVisitor):
    """AST visitor that checks for security violations."""

    def __init__(self) -> None:
        self.violations: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        """Check import statements."""
        for alias in node.names:
            module_name = alias.name.split('.')[0]  # Get top-level module
            if module_name in FORBIDDEN_MODULES:
                self.violations.append(f"Forbidden import: {alias.name}")
            elif module_name not in ALLOWED_MODULES and not self._is_submodule_of_allowed(alias.name):
                # If not in allowed list and not a submodule of allowed, it's forbidden
                self.violations.append(f"Module not in allowed list: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check from ... import statements."""
        if node.module:
            module_name = node.module.split('.')[0]
            if module_name in FORBIDDEN_MODULES:
                self.violations.append(f"Forbidden import: {node.module}")
            elif module_name not in ALLOWED_MODULES and not self._is_submodule_of_allowed(node.module):
                self.violations.append(f"Module not in allowed list: {node.module}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Check function calls."""
        func_name = self._get_function_name(node)
        if func_name and func_name in FORBIDDEN_FUNCTIONS:
            self.violations.append(f"Forbidden function call: {func_name}")

        # Check for attribute access like os.system
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in FORBIDDEN_FUNCTIONS:
                self.violations.append(f"Forbidden function call: {node.func.attr}")

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Check attribute access for dangerous patterns."""
        # Block access to __class__, __bases__, __subclasses__, etc.
        if node.attr.startswith('__') and node.attr.endswith('__'):
            dangerous_dunder = ['__class__', '__bases__', '__subclasses__', '__mro__',
                              '__globals__', '__code__', '__builtins__', '__import__']
            if node.attr in dangerous_dunder:
                self.violations.append(f"Forbidden attribute access: {node.attr}")

        self.generic_visit(node)

    def _get_function_name(self, node: ast.Call) -> str | None:
        """Extract function name from a Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            # For attribute access like "module.function"
            return node.func.attr
        return None

    def _is_submodule_of_allowed(self, module_name: str) -> bool:
        """Check if module is a submodule of an allowed module."""
        parts = module_name.split('.')
        for i in range(len(parts)):
            partial = '.'.join(parts[:i+1])
            if partial in ALLOWED_MODULES:
                return True
        return False


def sanitize_python(python_code: str) -> tuple[bool, str]:
    """Validate Python code for security issues using AST analysis.

    Args:
        python_code: Python source code to validate.

    Returns:
        Tuple of (is_safe, error_message). If is_safe is True, error_message is empty.
        If is_safe is False, error_message contains the security violation details.
    """
    if not python_code or not python_code.strip():
        return True, ""

    try:
        # Parse the code into an AST
        tree = ast.parse(python_code)
    except SyntaxError as e:
        return False, f"Syntax error in code: {e.msg} at line {e.lineno}"

    # Visit all nodes and check for violations
    visitor = SecurityVisitor()
    visitor.visit(tree)

    if visitor.violations:
        return False, f"Security violations detected: {'; '.join(visitor.violations)}"

    return True, ""
