"""Tests for security sanitizers."""

from src.execution.security.latex_sanitizer import sanitize_latex
from src.execution.security.python_sanitizer import sanitize_python


class TestLatexSanitizer:
    """Tests for LaTeX security sanitizer."""

    def test_allows_safe_latex(self):
        """Should allow safe LaTeX code."""
        safe_latex = r"""
        \documentclass{article}
        \begin{document}
        Hello World
        \end{document}
        """
        is_safe, error = sanitize_latex(safe_latex)
        assert is_safe is True
        assert error == ""

    def test_blocks_write18(self):
        """Should block \\write18 command."""
        malicious = r"\write18{rm -rf /}"
        is_safe, error = sanitize_latex(malicious)
        assert is_safe is False
        assert "write18" in error.lower()

    def test_blocks_shell_escape(self):
        """Should block shell-escape."""
        malicious = r"\documentclass[shell-escape]{article}"
        is_safe, error = sanitize_latex(malicious)
        assert is_safe is False

    def test_blocks_input_pipe(self):
        """Should block \\input{|...} pattern."""
        malicious = r"\input{|cat /etc/passwd}"
        is_safe, error = sanitize_latex(malicious)
        assert is_safe is False

    def test_blocks_catcode_manipulation(self):
        """Should block catcode manipulation."""
        malicious = r"\catcode`|=0"
        is_safe, error = sanitize_latex(malicious)
        assert is_safe is False

    def test_blocks_immediate_write(self):
        """Should block \\immediate\\write pattern."""
        malicious = r"\immediate\write18{ls}"
        is_safe, error = sanitize_latex(malicious)
        assert is_safe is False

    def test_blocks_lowercase_trick(self):
        """Should block lowercase command."""
        malicious = r"\lowercase{...}"
        is_safe, error = sanitize_latex(malicious)
        assert is_safe is False

    def test_blocks_openout(self):
        """Should block \\openout command."""
        malicious = r"\openout\myfile=output.txt"
        is_safe, error = sanitize_latex(malicious)
        assert is_safe is False

    def test_blocks_directlua(self):
        """Should block \\directlua command."""
        malicious = r"\directlua{os.execute('rm -rf /')}"
        is_safe, error = sanitize_latex(malicious)
        assert is_safe is False

    def test_allows_complex_safe_latex(self):
        """Should allow complex but safe LaTeX."""
        safe_latex = r"""
        \documentclass{article}
        \usepackage{amsmath}
        \usepackage{graphicx}
        \begin{document}
        \section{Introduction}
        Here is an equation: $E = mc^2$
        \includegraphics{figure.png}
        \end{document}
        """
        is_safe, error = sanitize_latex(safe_latex)
        assert is_safe is True
        assert error == ""

    def test_empty_code(self):
        """Should allow empty code."""
        is_safe, error = sanitize_latex("")
        assert is_safe is True
        assert error == ""


class TestPythonSanitizer:
    """Tests for Python AST sanitizer."""

    def test_allows_safe_imports(self):
        """Should allow safe imports."""
        safe_code = "import numpy as np\nimport matplotlib.pyplot as plt"
        is_safe, error = sanitize_python(safe_code)
        assert is_safe is True

    def test_blocks_os_import(self):
        """Should block os module import."""
        malicious = "import os\nos.system('rm -rf /')"
        is_safe, error = sanitize_python(malicious)
        assert is_safe is False
        assert "os" in error

    def test_blocks_subprocess_import(self):
        """Should block subprocess module."""
        malicious = "import subprocess"
        is_safe, error = sanitize_python(malicious)
        assert is_safe is False

    def test_blocks_eval(self):
        """Should block eval function."""
        malicious = "eval('__import__(\"os\").system(\"id\")')"
        is_safe, error = sanitize_python(malicious)
        assert is_safe is False

    def test_blocks_exec(self):
        """Should block exec function."""
        malicious = "exec('print(1)')"
        is_safe, error = sanitize_python(malicious)
        assert is_safe is False

    def test_allows_matplotlib_savefig(self):
        """Should allow matplotlib savefig."""
        safe_code = """
import matplotlib.pyplot as plt
plt.plot([1,2,3])
plt.savefig('output.png')
"""
        is_safe, error = sanitize_python(safe_code)
        assert is_safe is True

    def test_handles_syntax_error(self):
        """Should handle syntax errors gracefully."""
        invalid_code = "def broken("
        is_safe, error = sanitize_python(invalid_code)
        assert is_safe is False
        assert "syntax" in error.lower()

    def test_blocks_sys_import(self):
        """Should block sys module."""
        malicious = "import sys"
        is_safe, error = sanitize_python(malicious)
        assert is_safe is False

    def test_blocks_open_function(self):
        """Should block open function."""
        malicious = "open('/etc/passwd', 'r')"
        is_safe, error = sanitize_python(malicious)
        assert is_safe is False

    def test_blocks_compile_function(self):
        """Should block compile function."""
        malicious = "compile('print(1)', '<string>', 'exec')"
        is_safe, error = sanitize_python(malicious)
        assert is_safe is False

    def test_blocks_dunder_attribute_access(self):
        """Should block __class__ attribute access."""
        malicious = "''.__class__.__bases__"
        is_safe, error = sanitize_python(malicious)
        assert is_safe is False

    def test_allows_scipy(self):
        """Should allow scipy."""
        safe_code = "import scipy\nfrom scipy import optimize"
        is_safe, error = sanitize_python(safe_code)
        assert is_safe is True

    def test_allows_pandas(self):
        """Should allow pandas."""
        safe_code = "import pandas as pd\ndf = pd.DataFrame([1,2,3])"
        is_safe, error = sanitize_python(safe_code)
        assert is_safe is True

    def test_allows_safe_code_with_functions(self):
        """Should allow safe code with function definitions."""
        safe_code = """
import numpy as np

def calculate_mean(data):
    return np.mean(data)

result = calculate_mean([1, 2, 3, 4, 5])
"""
        is_safe, error = sanitize_python(safe_code)
        assert is_safe is True

    def test_allows_safe_code_with_classes(self):
        """Should allow safe code with class definitions."""
        safe_code = """
import numpy as np

class DataProcessor:
    def __init__(self, data):
        self.data = np.array(data)

    def process(self):
        return self.data * 2
"""
        is_safe, error = sanitize_python(safe_code)
        assert is_safe is True

    def test_empty_code(self):
        """Should allow empty code."""
        is_safe, error = sanitize_python("")
        assert is_safe is True
        assert error == ""

    def test_blocks_from_import_forbidden(self):
        """Should block from ... import for forbidden modules."""
        malicious = "from os import system"
        is_safe, error = sanitize_python(malicious)
        assert is_safe is False

    def test_allows_math_module(self):
        """Should allow math module."""
        safe_code = "import math\nprint(math.sqrt(16))"
        is_safe, error = sanitize_python(safe_code)
        assert is_safe is True

    def test_allows_json_module(self):
        """Should allow json module."""
        safe_code = "import json\ndata = json.loads('{\"key\": \"value\"}')"
        is_safe, error = sanitize_python(safe_code)
        assert is_safe is True
