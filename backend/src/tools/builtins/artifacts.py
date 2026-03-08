"""Artifact presentation tool."""

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class PresentFilesInput(BaseModel):
    """Input for present_files tool."""
    files: list[str] = Field(description="List of file paths to present to the user")


@tool(args_schema=PresentFilesInput)
async def present_files_tool(files: list[str]) -> str:
    """Present output files to the user.

    Use this tool to make generated files visible and downloadable for the user.
    Only files in the outputs directory can be presented.

    Args:
        files: List of file paths to present

    Returns:
        Confirmation of presented files
    """
    # Filter to only allow files in outputs directory
    valid_files = []
    for file_path in files:
        # Basic security check
        if "/outputs/" in file_path or file_path.startswith("outputs/"):
            valid_files.append(file_path)

    if not valid_files:
        return "No valid output files to present. Only files in outputs/ directory can be presented."

    return f"Presenting {len(valid_files)} file(s) to user:\n" + "\n".join(f"  - {f}" for f in valid_files)
