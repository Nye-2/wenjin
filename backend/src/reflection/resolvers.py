"""Dynamic module loading via path strings like 'module.path:variable_name'."""
from typing import Any

import importlib
import os

MODULE_TO_PACKAGE_HINTS = {
    "langchain_google_genai": "langchain-google-genai",
    "langchain_anthropic": "langchain-anthropic",
    "langchain_openai": "langchain-openai",
    "langchain_deepseek": "langchain-deepseek",
}


def resolve_variable[T](
    variable_path: str,
    expected_type: type[T] | tuple[type, ...] | None = None,
) -> T:
    """Resolve a variable from 'module.path:variable_name'.

    Args:
        variable_path: Path like "langchain_openai:ChatOpenAI"
        expected_type: Optional type validation

    Returns:
        The resolved variable

    Raises:
        ValueError: If path format is invalid
        ImportError: If module not found (with actionable hint)
    """
    if ":" not in variable_path:
        msg = f"Invalid variable path '{variable_path}'. Expected format: 'module.path:variable_name'"
        raise ValueError(msg)

    module_path, variable_name = variable_path.rsplit(":", 1)

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        top_module = module_path.split(".")[0]
        package_hint = MODULE_TO_PACKAGE_HINTS.get(top_module)
        hint = f" Install it with `uv add {package_hint}`." if package_hint else ""
        msg = f"Missing dependency '{top_module}'.{hint}"
        raise ImportError(msg) from e

    if not hasattr(module, variable_name):
        msg = f"Module '{module_path}' has no attribute '{variable_name}'"
        raise AttributeError(msg)

    variable = getattr(module, variable_name)

    if expected_type is not None and not isinstance(variable, expected_type):
        msg = f"Expected {expected_type}, got {type(variable)}"
        raise TypeError(msg)

    return variable


def resolve_class[T](class_path: str, base_class: type[T] | None = None) -> type[T]:
    """Resolve a class from path and optionally validate its base class."""
    cls = resolve_variable(class_path, expected_type=type)
    if base_class is not None and not issubclass(cls, base_class):
        msg = f"Expected subclass of {base_class.__name__}, got {cls.__name__}"
        raise TypeError(msg)
    return cls


def resolve_env_variables(data: Any) -> Any:
    """Recursively resolve $ENV_VAR references in config data."""
    if isinstance(data, str) and data.startswith("$"):
        return os.getenv(data[1:], "")
    if isinstance(data, dict):
        return {k: resolve_env_variables(v) for k, v in data.items()}
    if isinstance(data, list):
        return [resolve_env_variables(item) for item in data]
    return data
