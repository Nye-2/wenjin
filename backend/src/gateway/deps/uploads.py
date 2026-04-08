"""Upload-domain dependency factories."""

from src.services.upload_preprocessor import (
    UploadPreprocessor,
    get_upload_preprocessor_service,
)


async def get_upload_preprocessor() -> UploadPreprocessor:
    """Get upload preprocessor service instance."""
    return get_upload_preprocessor_service()
