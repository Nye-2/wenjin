"""Deterministic integrity checks for raster academic visual candidates."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageStat, UnidentifiedImageError


class RasterQualityError(ValueError):
    """Raised when candidate bytes are invalid or visually empty."""


def inspect_raster(
    content: bytes,
    *,
    expected_mime_type: str,
    minimum_dimension: int,
) -> dict[str, int | float | bool]:
    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            actual_mime = Image.MIME.get(image.format or "")
            if actual_mime != expected_mime_type:
                raise RasterQualityError("raster MIME does not match decoded content")
            width, height = image.size
            if width < minimum_dimension or height < minimum_dimension:
                raise RasterQualityError("raster dimensions are below the academic visual minimum")
            sample = image.convert("RGB")
            sample.thumbnail((128, 128))
            luminance = sample.convert("L")
            deviation = float(ImageStat.Stat(luminance).stddev[0])
            extrema = luminance.getextrema()
    except (OSError, UnidentifiedImageError) as exc:
        raise RasterQualityError("raster candidate cannot be decoded") from exc
    if extrema is None or extrema[0] == extrema[1] or deviation < 0.5:
        raise RasterQualityError("raster candidate is blank or visually empty")
    return {
        "decoded": True,
        "width": width,
        "height": height,
        "luminance_stddev": round(deviation, 3),
        "nonblank": True,
    }


__all__ = ["RasterQualityError", "inspect_raster"]
