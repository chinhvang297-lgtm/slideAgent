"""PPT template parser: extracts structural information from PPTX files."""

import asyncio
import base64
import io
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.util import Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import PP_PLACEHOLDER

from ..utils import get_logger

logger = get_logger(__name__)

_PLACEHOLDER_TYPE_NAMES = {
    1: "title",
    2: "body",
    3: "center_title",
    4: "subtitle",
    10: "date",
    11: "footer",
    12: "slide_number",
    15: "table",
    16: "chart",
    18: "picture",
    19: "bitmap",
}


def _rgb_to_hex(rgb: RGBColor | None) -> str | None:
    if rgb is None:
        return None
    return f"#{rgb.rgb:06X}"


def _emu_to_ratio(emu: int, total: int) -> float:
    return round(emu / total, 4) if total > 0 else 0.0


def _parse_font(run_or_para) -> dict[str, Any]:
    """Extract font properties from a run or paragraph."""
    font = {}
    try:
        f = run_or_para.font
        font["name"] = f.name
        font["size"] = int(f.size.pt) if f.size else None
        font["bold"] = f.bold
        font["italic"] = f.italic
        font["color"] = _rgb_to_hex(f.color.rgb) if f.color and f.color.type else None
    except Exception:
        pass
    return font


def _parse_placeholder(shape, slide_width: int, slide_height: int) -> dict[str, Any]:
    """Parse a single placeholder shape into structured data."""
    ph = shape.placeholder_format
    ph_type = _PLACEHOLDER_TYPE_NAMES.get(ph.type if ph else 0, "unknown")

    left = _emu_to_ratio(shape.left or 0, slide_width)
    top = _emu_to_ratio(shape.top or 0, slide_height)
    width = _emu_to_ratio(shape.width or 0, slide_width)
    height = _emu_to_ratio(shape.height or 0, slide_height)

    placeholder: dict[str, Any] = {
        "idx": ph.idx if ph else 0,
        "type": ph_type,
        "name": shape.name,
        "position": {"left": left, "top": top, "width": width, "height": height},
        "font": {},
        "alignment": "left",
        "sample_text": "",
    }

    if shape.has_text_frame:
        tf = shape.text_frame
        all_text = tf.text.strip()
        placeholder["sample_text"] = all_text[:100] if all_text else ""

        # Extract font from first non-empty paragraph
        for para in tf.paragraphs:
            if para.runs:
                placeholder["font"] = _parse_font(para.runs[0])
                align = para.alignment
                if align == PP_ALIGN.CENTER:
                    placeholder["alignment"] = "center"
                elif align == PP_ALIGN.RIGHT:
                    placeholder["alignment"] = "right"
                else:
                    placeholder["alignment"] = "left"
                break

    return placeholder


def _parse_slide(slide, slide_index: int, slide_width: int, slide_height: int) -> dict[str, Any]:
    """Parse a single slide into structured data."""
    placeholders = []
    images = []

    for shape in slide.shapes:
        if shape.is_placeholder:
            placeholders.append(_parse_placeholder(shape, slide_width, slide_height))
        elif shape.shape_type == 13:  # Picture
            images.append({"name": shape.name, "shape_type": "picture"})

    # Determine background color
    bg_color = None
    try:
        bg = slide.background
        fill = bg.fill
        if fill.type is not None and str(fill.type) == "SOLID (1)":
            bg_color = _rgb_to_hex(fill.fore_color.rgb)
    except Exception:
        pass

    # Classify layout type based on placeholders
    layout_type = _classify_layout(placeholders)

    return {
        "index": slide_index,
        "layout_type": layout_type,
        "layout_name": slide.slide_layout.name if slide.slide_layout else "",
        "background_color": bg_color,
        "placeholders": placeholders,
        "has_images": len(images) > 0,
        "image_count": len(images),
    }


def _classify_layout(placeholders: list[dict]) -> str:
    """Classify layout type based on placeholder arrangement."""
    types = {p["type"] for p in placeholders}
    ph_count = len(placeholders)

    if "center_title" in types:
        return "title_slide"
    if "title" in types and ph_count == 1:
        return "section_header"
    if "title" in types and ("picture" in types or "bitmap" in types):
        if any(p["position"]["left"] < 0.45 for p in placeholders if p["type"] in ("picture", "bitmap")):
            return "image_left"
        return "image_right"
    if "title" in types and "body" in types:
        # Check if it looks like two-column
        body_phs = [p for p in placeholders if p["type"] == "body"]
        if len(body_phs) >= 2:
            return "two_column"
        return "content"
    if "picture" in types and "title" not in types:
        return "image_only"
    if ph_count == 0:
        return "blank"
    return "content"


def parse_template(pptx_path: str | Path) -> dict[str, Any]:
    """
    Parse a PPTX template file and return a structured schema.

    Returns:
        dict with keys: slides, color_scheme, font_scheme, slide_dimensions
    """
    pptx_path = Path(pptx_path)
    logger.info(f"Parsing template: {pptx_path.name}")

    prs = Presentation(str(pptx_path))
    slide_width = prs.slide_width
    slide_height = prs.slide_height

    slides = []
    for i, slide in enumerate(prs.slides):
        slide_data = _parse_slide(slide, i, slide_width, slide_height)
        slides.append(slide_data)
        logger.debug(f"  Slide {i}: {slide_data['layout_type']} ({len(slide_data['placeholders'])} placeholders)")

    from .style_extractor import extract_styles
    from .layout_analyzer import analyze_layouts

    styles = extract_styles(prs)
    layout_groups = analyze_layouts(slides)

    schema = {
        "template_path": str(pptx_path),
        "slide_count": len(slides),
        "slide_dimensions": {
            "width_emu": slide_width,
            "height_emu": slide_height,
            "width_pt": round(slide_width / 914400 * 72, 2),
            "height_pt": round(slide_height / 914400 * 72, 2),
        },
        "slides": slides,
        "layout_groups": layout_groups,
        "color_scheme": styles["color_scheme"],
        "font_scheme": styles["font_scheme"],
    }

    logger.info(f"Template parsed: {len(slides)} slides, {len(layout_groups)} layout groups")
    return schema


async def ppt_to_images_async(pptx_path: str | Path, output_dir: Path) -> list[Path]:
    """
    Convert PPT slides to images asynchronously.
    Uses LibreOffice if available, otherwise generates placeholder thumbnails.
    """
    import subprocess
    import shutil

    pptx_path = Path(pptx_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Try LibreOffice conversion
    if shutil.which("libreoffice") or shutil.which("soffice"):
        cmd = shutil.which("libreoffice") or shutil.which("soffice")
        try:
            proc = await asyncio.create_subprocess_exec(
                cmd, "--headless", "--convert-to", "png",
                "--outdir", str(output_dir), str(pptx_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            images = sorted(output_dir.glob("*.png"))
            if images:
                logger.info(f"Generated {len(images)} slide images via LibreOffice")
                return images
        except Exception as e:
            logger.warning(f"LibreOffice conversion failed: {e}")

    # Fallback: generate placeholder images using Pillow
    return await _generate_placeholder_images(pptx_path, output_dir)


async def _generate_placeholder_images(pptx_path: Path, output_dir: Path) -> list[Path]:
    """Generate simple placeholder slide thumbnails."""
    from PIL import Image, ImageDraw, ImageFont
    from pptx import Presentation

    prs = Presentation(str(pptx_path))
    images = []

    for i, slide in enumerate(prs.slides):
        img = Image.new("RGB", (960, 540), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # Draw slide number
        draw.rectangle([0, 0, 960, 540], outline=(200, 200, 200), width=2)
        draw.text((480, 270), f"Slide {i + 1}", fill=(100, 100, 100), anchor="mm")

        # Draw text content snippets
        y_offset = 60
        for shape in slide.shapes:
            if shape.has_text_frame and y_offset < 480:
                text = shape.text_frame.text[:80].strip()
                if text:
                    draw.text((40, y_offset), text[:60], fill=(50, 50, 50))
                    y_offset += 30

        out_path = output_dir / f"slide_{i:03d}.png"
        img.save(str(out_path))
        images.append(out_path)

    logger.info(f"Generated {len(images)} placeholder slide images")
    return images


def collect_images(pptx_path: str | Path, output_dir: Path) -> list[dict[str, Any]]:
    """Extract all embedded images from a PPTX file."""
    pptx_path = Path(pptx_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    prs = Presentation(str(pptx_path))
    collected = []

    for slide_idx, slide in enumerate(prs.slides):
        for shape_idx, shape in enumerate(slide.shapes):
            if shape.shape_type == 13:  # MSO_SHAPE_TYPE.PICTURE
                try:
                    image = shape.image
                    ext = image.ext
                    blob = image.blob
                    out_path = output_dir / f"slide{slide_idx}_img{shape_idx}.{ext}"
                    out_path.write_bytes(blob)
                    collected.append({
                        "slide_index": slide_idx,
                        "shape_name": shape.name,
                        "path": str(out_path),
                        "ext": ext,
                        "size_bytes": len(blob),
                    })
                except Exception as e:
                    logger.debug(f"Could not extract image from slide {slide_idx}: {e}")

    logger.info(f"Collected {len(collected)} images from template")
    return collected
