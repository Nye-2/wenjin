"""Deterministic exact-label overlay for hybrid academic illustrations."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.contracts.figure_generation import ExactVisualLabel

OVERLAY_CONTRACT_VERSION = "wenjin.academic_visual.overlay.v1"

_ANCHORS: dict[str, tuple[float, float, str]] = {
    "top_left": (0.04, 0.04, "left"),
    "top_center": (0.50, 0.04, "center"),
    "top_right": (0.96, 0.04, "right"),
    "center_left": (0.04, 0.50, "left"),
    "center": (0.50, 0.50, "center"),
    "center_right": (0.96, 0.50, "right"),
    "bottom_left": (0.04, 0.96, "left"),
    "bottom_center": (0.50, 0.96, "center"),
    "bottom_right": (0.96, 0.96, "right"),
}
_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/PingFang.ttc",
)


def overlay_exact_labels(content: bytes, labels: tuple[ExactVisualLabel, ...]) -> bytes:
    if not labels:
        raise ValueError("hybrid_overlay_requires_labels")
    with Image.open(io.BytesIO(content)) as source:
        image = source.convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    font = _font(max(16, min(image.width, image.height) // 34))
    occupied: set[str] = set()
    for label in labels:
        if label.semantic_anchor in occupied:
            raise ValueError("hybrid_overlay_anchor_collision")
        occupied.add(label.semantic_anchor)
        _draw_label(draw, image.size, label.text, label.semantic_anchor, font)
    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


def overlay_manifest_hash(labels: tuple[ExactVisualLabel, ...]) -> str:
    """Bind a hybrid candidate to the deterministic overlay contract and labels."""

    payload = {
        "contract_version": OVERLAY_CONTRACT_VERSION,
        "labels": [label.model_dump(mode="json") for label in labels],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _draw_label(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    text: str,
    anchor: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    x_ratio, y_ratio, align = _ANCHORS[anchor]
    width, height = size
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    text_width = right - left
    text_height = bottom - top
    padding_x = max(8, text_height // 2)
    padding_y = max(5, text_height // 4)
    x = int(width * x_ratio)
    y = int(height * y_ratio)
    if align == "center":
        x -= text_width // 2
    elif align == "right":
        x -= text_width
    if anchor.startswith("bottom_"):
        y -= text_height
    elif anchor.startswith("center"):
        y -= text_height // 2
    x = min(max(padding_x, x), width - text_width - padding_x)
    y = min(max(padding_y, y), height - text_height - padding_y)
    box = (
        x - padding_x,
        y - padding_y,
        x + text_width + padding_x,
        y + text_height + padding_y,
    )
    radius = max(5, text_height // 3)
    draw.rounded_rectangle(box, radius=radius, fill=(255, 255, 255, 232), outline=(24, 38, 36, 210), width=2)
    draw.text((x, y - top), text, font=font, fill=(16, 26, 24, 255))


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default(size=size)


__all__ = [
    "OVERLAY_CONTRACT_VERSION",
    "overlay_exact_labels",
    "overlay_manifest_hash",
]
