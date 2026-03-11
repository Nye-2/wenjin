"""LaTeX security sanitizer.

This module provides security validation for LaTeX code to prevent
arbitrary code execution and system access.
"""

import re
from typing import Tuple


def sanitize_latex(latex_code: str) -> Tuple[bool, str]:
    """Validate LaTeX code for security issues.

    Args:
        latex_code: LaTeX source code to validate.

    Returns:
        Tuple of (is_safe, error_message). If is_safe is True, error_message is empty.
        If is_safe is False, error_message contains the security violation details.
    """
    if not latex_code or not latex_code.strip():
        return True, ""

    # Convert to lowercase for case-insensitive matching
    code_lower = latex_code.lower()

    # List of dangerous patterns to check
    dangerous_patterns = [
        # Shell execution commands
        (r'\\write18\b', "write18 command is not allowed (shell execution)"),
        (r'\\immediate\s*\\write', "immediate write command is not allowed"),

        # Shell escape option
        (r'shell-escape', "shell-escape option is not allowed"),
        (r'enable-write18', "enable-write18 option is not allowed"),
        (r'write18=', "write18 option is not allowed"),

        # Input with pipe (command execution)
        (r'\\input\s*\{[^}]*\|', "input with pipe is not allowed (command execution)"),
        (r'\\include\s*\{[^}]*\|', "include with pipe is not allowed"),

        # Catcode manipulation (can redefine characters)
        (r'\\catcode\b', "catcode manipulation is not allowed"),
        (r'\\endlinechar\b', "endlinechar manipulation is not allowed"),

        # Lowercase/uppercase tricks
        (r'\\lowercase\b', "lowercase command is not allowed"),
        (r'\\uppercase\b', "uppercase command is not allowed"),

        # csname for building command names dynamically
        (r'\\csname\b.*\\endcsname\b', "csname/endcsname is not allowed"),

        # Input/Output redirection
        (r'\\openin\b', "openin command is not allowed"),
        (r'\\openout\b', "openout command is not allowed"),
        (r'\\closein\b', "closein command is not allowed"),
        (r'\\closeout\b', "closeout command is not allowed"),

        # Reading files
        (r'\\read\s+\d+', "read command is not allowed"),

        # External commands
        (r'\\externaldocument\b', "externaldocument is not allowed"),
        (r'\\ShellEscape\b', "ShellEscape command is not allowed"),

        # TikZ externalize can execute commands
        (r'external/externalize', "tikz externalize is not allowed"),

        # Lua code execution (LuaLaTeX)
        (r'\\directlua\b', "directlua command is not allowed"),
        (r'\\luaexec\b', "luaexec command is not allowed"),

        # Python code execution (PythonTeX)
        (r'\\py\b', "py command is not allowed"),
        (r'\\pyc\b', "pyc command is not allowed"),
        (r'\\pyfile\b', "pyfile command is not allowed"),

        # System commands
        (r'\\system\b', "system command is not allowed"),
        (r'\\epstopdf\b', "epstopdf command is not allowed"),
    ]

    # Check each pattern
    for pattern, message in dangerous_patterns:
        if re.search(pattern, code_lower, re.IGNORECASE | re.DOTALL):
            return False, f"Security violation: {message}"

    # Additional check for common obfuscation attempts
    # Check for backticks with special characters (used in some attacks)
    if re.search(r'\\catcode\s*`', latex_code, re.IGNORECASE):
        return False, "Security violation: catcode manipulation is not allowed"

    # Check for consecutive backslashes that might be trying to escape detection
    # But allow legitimate LaTeX commands
    if re.search(r'\\\\[a-zA-Z]+18', latex_code, re.IGNORECASE):
        return False, "Security violation: suspicious command pattern detected"

    return True, ""
