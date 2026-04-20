"""Style extractor: extracts color and font schemes from PPTX presentations."""

from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor

from ..utils import get_logger

logger = get_logger(__name__)


def _rgb_to_hex(rgb: RGBColor | None) -> str | None:
    if rgb is None:
        return None
    try:
        return f"#{rgb.rgb:06X}"
    except Exception:
        return None


def extract_styles(prs: Presentation) -> dict[str, Any]:
    """Extract color and font schemes from a presentation."""
    color_scheme = _extract_color_scheme(prs)
    font_scheme = _extract_font_scheme(prs)

    return {
        "color_scheme": color_scheme,
        "font_scheme": font_scheme,
    }


def _extract_color_scheme(prs: Presentation) -> dict[str, str | None]:
    """Extract the theme color scheme."""
    scheme: dict[str, str | None] = {
        "primary": None,
        "secondary": None,
        "accent1": None,
        "accent2": None,
        "text_dark": None,
        "text_light": None,
        "background1": None,
        "background2": None,
    }

    try:
        theme = prs.slide_master.theme_color_map
    except Exception:
        theme = None

    # Try to extract from slide master shapes
    try:
        master = prs.slide_master
        _collect_colors_from_shapes(master.shapes, scheme)
    except Exception:
        pass

    # Try first slide background
    if prs.slides:
        try:
            bg = prs.slides[0].background
            fill = bg.fill
            if fill.type is not None:
                color = _rgb_to_hex(fill.fore_color.rgb)
                if color:
                    scheme["background1"] = color
        except Exception:
            pass

    return scheme


def _collect_colors_from_shapes(shapes, scheme: dict) -> None:
    """Collect color information from shapes."""
    colors_seen = []

    for shape in shapes:
        try:
            if hasattr(shape, "fill"):
                fill = shape.fill
                if fill.type is not None:
                    color = _rgb_to_hex(fill.fore_color.rgb)
                    if color and color not in colors_seen:
                        colors_seen.append(color)
        except Exception:
            pass

        try:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        try:
                            color = _rgb_to_hex(run.font.color.rgb)
                            if color and color not in colors_seen:
                                colors_seen.append(color)
                        except Exception:
                            pass
        except Exception:
            pass

    # Assign collected colors to scheme slots
    keys = ["primary", "secondary", "accent1", "accent2"]
    for i, color in enumerate(colors_seen[:4]):
        if scheme[keys[i]] is None:
            scheme[keys[i]] = color


def _extract_font_scheme(prs: Presentation) -> dict[str, str | None]:
    """Extract font scheme (heading and body fonts)."""
    font_scheme: dict[str, str | None] = {
        "heading": None,
        "body": None,
    }

    # Try to get fonts from slide master
    try:
        master = prs.slide_master
        for layout in master.slide_layouts:
            for ph in layout.placeholders:
                if ph.has_text_frame:
                    for para in ph.text_frame.paragraphs:
                        for run in para.runs:
                            if run.font.name:
                                ph_type = ph.placeholder_format.type if ph.placeholder_format else None
                                if ph_type in (1, 3):  # TITLE or CENTER_TITLE
                                    if not font_scheme["heading"]:
                                        font_scheme["heading"] = run.font.name
                                elif ph_type == 2:  # BODY
                                    if not font_scheme["body"]:
                                        font_scheme["body"] = run.font.name
    except Exception:
        pass

    # Fallback from first slide
    if (not font_scheme["heading"] or not font_scheme["body"]) and prs.slides:
        try:
            for shape in prs.slides[0].shapes:
                if shape.is_placeholder and shape.has_text_frame:
                    ph_type = shape.placeholder_format.type if shape.placeholder_format else None
                    for para in shape.text_frame.paragraphs:
                        for run in para.runs:
                            if run.font.name:
                                if ph_type in (1, 3) and not font_scheme["heading"]:
                                    font_scheme["heading"] = run.font.name
                                elif ph_type == 2 and not font_scheme["body"]:
                                    font_scheme["body"] = run.font.name
        except Exception:
            pass

    # Final fallback to Calibri
    if not font_scheme["heading"]:
        font_scheme["heading"] = "Calibri"
    if not font_scheme["body"]:
        font_scheme["body"] = "Calibri"

    return font_scheme
