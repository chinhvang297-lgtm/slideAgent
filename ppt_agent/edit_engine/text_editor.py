"""Text editor: replace and format text in PPTX placeholders."""

import copy
from typing import Any

from pptx.shapes.base import BaseShape
from pptx.util import Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

from ..utils import get_logger

logger = get_logger(__name__)


def replace_span(shape: BaseShape, new_text: str) -> None:
    """
    Replace all text in a shape's text frame while preserving formatting.
    Simulates human "select all → type" editing behavior.
    """
    if not shape.has_text_frame:
        return

    tf = shape.text_frame

    if not tf.paragraphs:
        tf.add_paragraph().text = new_text
        return

    # Get formatting from first paragraph/run for preservation
    first_para = tf.paragraphs[0]
    preserved_font = _extract_font_props(first_para)
    preserved_alignment = first_para.alignment

    # Clear all paragraphs
    _clear_text_frame(tf)

    # Set new text in first paragraph
    para = tf.paragraphs[0]
    _apply_font_props(para, preserved_font)
    if preserved_alignment:
        para.alignment = preserved_alignment
    para.text = new_text


def set_paragraph_text(
    shape: BaseShape,
    paragraphs: list[str],
    is_bullet_list: bool = False,
) -> None:
    """
    Set multiple paragraphs in a text frame.
    Preserves existing paragraph formatting from the first paragraph.
    """
    if not shape.has_text_frame:
        return

    tf = shape.text_frame
    if not tf.paragraphs:
        para = tf.add_paragraph()
        para.text = paragraphs[0] if paragraphs else ""
        return

    # Capture formatting from first paragraph
    first_para = tf.paragraphs[0]
    preserved_font = _extract_font_props(first_para)
    preserved_para_props = _extract_para_props(first_para)

    # Clear existing content
    _clear_text_frame(tf)

    # Write new paragraphs
    for i, text in enumerate(paragraphs):
        if i == 0:
            para = tf.paragraphs[0]
        else:
            para = tf.add_paragraph()

        # Apply preserved formatting
        _apply_para_props(para, preserved_para_props)
        _apply_font_props(para, preserved_font)

        if is_bullet_list:
            # Add bullet character prefix for visual consistency
            run = para.add_run()
            run.text = text
        else:
            para.text = text


def _extract_font_props(para) -> dict[str, Any]:
    """Extract font properties from a paragraph."""
    props: dict[str, Any] = {}
    try:
        if para.runs:
            font = para.runs[0].font
            props["name"] = font.name
            props["size"] = font.size
            props["bold"] = font.bold
            props["italic"] = font.italic
            try:
                props["color"] = font.color.rgb if font.color and font.color.type else None
            except Exception:
                props["color"] = None
    except Exception:
        pass
    return props


def _extract_para_props(para) -> dict[str, Any]:
    """Extract paragraph-level properties."""
    props: dict[str, Any] = {}
    try:
        props["alignment"] = para.alignment
        props["level"] = para.level
    except Exception:
        pass
    return props


def _apply_font_props(para, props: dict[str, Any]) -> None:
    """Apply font properties to a paragraph."""
    if not props:
        return
    try:
        for run in para.runs:
            font = run.font
            if props.get("name"):
                font.name = props["name"]
            if props.get("size"):
                font.size = props["size"]
            if props.get("bold") is not None:
                font.bold = props["bold"]
            if props.get("italic") is not None:
                font.italic = props["italic"]
            if props.get("color"):
                try:
                    font.color.rgb = props["color"]
                except Exception:
                    pass
    except Exception:
        pass


def _apply_para_props(para, props: dict[str, Any]) -> None:
    """Apply paragraph properties."""
    if not props:
        return
    try:
        if props.get("alignment") is not None:
            para.alignment = props["alignment"]
        if props.get("level") is not None:
            para.level = props["level"]
    except Exception:
        pass


def _clear_text_frame(tf) -> None:
    """Clear all text from a text frame, keeping first paragraph."""
    from lxml import etree
    from pptx.oxml.ns import qn

    txBody = tf._txBody

    # Remove all paragraphs except first
    paras = txBody.findall(qn("a:p"))
    for para in paras[1:]:
        txBody.remove(para)

    # Clear first paragraph
    if paras:
        first_para = paras[0]
        # Remove all runs and line breaks but keep paragraph properties
        for child in list(first_para):
            if child.tag in (qn("a:r"), qn("a:br"), qn("a:fld")):
                first_para.remove(child)
