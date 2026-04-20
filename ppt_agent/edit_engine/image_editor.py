"""Image editor: insert and resize images in PPTX slides."""

from pathlib import Path
from typing import Any

from pptx.util import Emu, Inches, Pt
from pptx.shapes.base import BaseShape

from ..utils import get_logger

logger = get_logger(__name__)


def insert_image(
    slide,
    image_path: str | Path,
    left: float = 0.1,
    top: float = 0.1,
    width: float = 0.5,
    height: float = 0.5,
    slide_width_emu: int = 9144000,
    slide_height_emu: int = 6858000,
) -> Any:
    """
    Insert an image into a slide at normalized coordinates.

    Args:
        slide: python-pptx Slide object
        image_path: Path to image file
        left, top, width, height: Normalized coordinates (0.0-1.0)
        slide_width_emu, slide_height_emu: Slide dimensions in EMU
    """
    image_path = Path(image_path)
    if not image_path.exists():
        logger.warning(f"Image not found: {image_path}")
        return None

    left_emu = Emu(int(left * slide_width_emu))
    top_emu = Emu(int(top * slide_height_emu))
    width_emu = Emu(int(width * slide_width_emu))
    height_emu = Emu(int(height * slide_height_emu))

    try:
        picture = slide.shapes.add_picture(
            str(image_path),
            left_emu,
            top_emu,
            width_emu,
            height_emu,
        )
        logger.debug(f"Inserted image: {image_path.name}")
        return picture
    except Exception as e:
        logger.warning(f"Failed to insert image {image_path}: {e}")
        return None


def insert_image_into_placeholder(
    shape: BaseShape,
    image_path: str | Path,
) -> bool:
    """
    Insert an image into a picture placeholder shape.

    Args:
        shape: Picture placeholder shape
        image_path: Path to image file
    """
    image_path = Path(image_path)
    if not image_path.exists():
        logger.warning(f"Image not found: {image_path}")
        return False

    try:
        # Use the placeholder's insert_picture method
        if hasattr(shape, "insert_picture"):
            shape.insert_picture(str(image_path))
            logger.debug(f"Inserted image into placeholder: {image_path.name}")
            return True

        # Fallback: add picture at placeholder position
        slide = shape.part.slide
        left = shape.left
        top = shape.top
        width = shape.width
        height = shape.height

        slide.shapes.add_picture(str(image_path), left, top, width, height)
        return True

    except Exception as e:
        logger.warning(f"Failed to insert image into placeholder: {e}")
        return False


def resize_image(image_path: str | Path, max_width: int = 1024, max_height: int = 768) -> Path:
    """
    Resize an image to fit within max dimensions, preserving aspect ratio.

    Returns path to resized image (may be same as input if no resize needed).
    """
    image_path = Path(image_path)
    if not image_path.exists():
        return image_path

    try:
        from PIL import Image

        img = Image.open(image_path)
        w, h = img.size

        if w <= max_width and h <= max_height:
            return image_path

        # Calculate new dimensions preserving aspect ratio
        ratio = min(max_width / w, max_height / h)
        new_w = int(w * ratio)
        new_h = int(h * ratio)

        resized = img.resize((new_w, new_h), Image.LANCZOS)

        # Save to temp file
        out_path = image_path.parent / f"resized_{image_path.name}"
        resized.save(str(out_path))
        logger.debug(f"Resized image {image_path.name}: {w}×{h} → {new_w}×{new_h}")
        return out_path

    except ImportError:
        logger.debug("Pillow not available for image resizing")
        return image_path
    except Exception as e:
        logger.warning(f"Failed to resize image {image_path}: {e}")
        return image_path
