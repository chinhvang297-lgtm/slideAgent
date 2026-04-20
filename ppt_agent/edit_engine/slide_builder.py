"""
Slide builder: builds the final PPTX by adding clean slides from template layouts.

Uses prs.slides.add_slide(layout) instead of cloning, which avoids template-text
contamination ("Section Title", "First bullet point..." bleeding into every slide).
"""

import shutil
from pathlib import Path
from typing import Any, Callable

from pptx import Presentation
from pptx.oxml.ns import qn

from .text_editor import replace_span, set_paragraph_text
from .image_editor import insert_image, insert_image_into_placeholder
from .validator import validate_page
from ..utils import get_logger

logger = get_logger(__name__)

# Placeholder type integers (from python-pptx / OOXML)
_TITLE_TYPES = {1, 3}          # TITLE=1, CENTER_TITLE=3
_BODY_TYPES = {2, 4, 7}        # BODY=2, SUBTITLE=4, OBJECT=7
_SYSTEM_TYPES = {10, 11, 12, 13, 15, 16}  # date/footer/slide_number


def build_presentation(
    template_path: str | Path,
    slide_plan: dict[str, Any],
    template_schema: dict[str, Any],
    output_path: str | Path,
    progress_callback: Callable[[str], None] | None = None,
) -> Path:
    template_path = Path(template_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Work on a copy of the template so all layouts/master/theme are inherited
    shutil.copy2(str(template_path), str(output_path))
    prs = Presentation(str(output_path))

    layout_map = _build_layout_map(prs)
    logger.info(f"Layout map: {list(layout_map.keys())}")

    layout_groups = {g["group_id"]: g for g in template_schema.get("layout_groups", [])}
    content_group = next(
        (g for g in layout_groups.values() if g.get("layout_type") == "content"),
        next(iter(layout_groups.values())) if layout_groups else None,
    )
    content_layout = layout_map.get("content") or prs.slide_layouts[1]

    slides = slide_plan.get("slides", [])
    original_count = len(prs.slides)
    total = len(slides)
    logger.info(f"Building presentation: {total} slides")

    all_issues = []
    for i, slide_spec in enumerate(slides):
        if progress_callback:
            progress_callback(f"Building slide {i+1}/{total}: {slide_spec.get('title', '')}")

        group_id = slide_spec.get("layout_group_id", 0)
        group = layout_groups.get(group_id)
        if group is None:
            group = content_group

        layout_type = group.get("layout_type", "content") if group else "content"

        # Never use section_header/title_slide template for content slides (i > 0)
        if i > 0 and layout_type in ("section_header", "title_slide"):
            layout_type = "content"

        layout = layout_map.get(layout_type) or content_layout
        new_slide = prs.slides.add_slide(layout)
        _populate_slide(new_slide, slide_spec, prs.slide_width, prs.slide_height)

        issues = validate_page(new_slide, i)
        all_issues.extend(issues)

        logger.debug(
            f"  Slide {i+1}: '{slide_spec.get('title','')}' "
            f"layout_type={layout_type} layout='{layout.name}'"
        )

    # Remove the original template slides
    for _ in range(original_count):
        _remove_slide(prs, 0)

    if all_issues:
        logger.warning(f"Validation found {len(all_issues)} issues")

    prs.save(str(output_path))
    logger.info(f"Presentation saved: {output_path}")
    return output_path


def _build_layout_map(prs: Presentation) -> dict[str, Any]:
    """Map layout-type names to slide_layout objects by inspecting placeholder types."""
    layout_map: dict[str, Any] = {}

    for layout in prs.slide_layouts:
        ph_types: set[int] = set()
        for ph in layout.placeholders:
            try:
                ph_types.add(int(ph.placeholder_format.type))
            except Exception:
                pass

        content_types = ph_types - _SYSTEM_TYPES
        has_center = 3 in content_types
        has_title = 1 in content_types
        has_object = 7 in content_types
        has_body = 2 in content_types
        has_subtitle = 4 in content_types
        has_picture = 18 in content_types
        object_count = sum(1 for t in content_types if t == 7)

        if has_center and has_subtitle and "title_slide" not in layout_map:
            layout_map["title_slide"] = layout
        elif has_title and has_object and not has_picture and object_count == 1 and "content" not in layout_map:
            layout_map["content"] = layout
        elif has_title and has_body and not has_object and "section_header" not in layout_map:
            layout_map["section_header"] = layout
        elif has_title and has_object and object_count >= 2 and "two_column" not in layout_map:
            layout_map["two_column"] = layout
        elif has_title and has_picture and "image" not in layout_map:
            layout_map["image"] = layout
        elif has_title and not has_object and not has_body and not has_subtitle and "title_only" not in layout_map:
            layout_map["title_only"] = layout

    return layout_map


def _remove_slide(prs: Presentation, index: int) -> None:
    """Remove the slide at the given 0-based index."""
    xml_slides = prs.slides._sldIdLst
    slide_elem = xml_slides[index]
    rid = slide_elem.get(qn("r:id"))
    prs.part.drop_rel(rid)
    xml_slides.remove(slide_elem)


def _populate_slide(
    slide,
    slide_spec: dict[str, Any],
    slide_width: int,
    slide_height: int,
) -> None:
    """Fill a clean layout-based slide with content from slide_spec."""
    title_text = slide_spec.get("title", "")
    content_blocks = slide_spec.get("content_blocks", [])

    # Identify title and body placeholders by type
    title_ph = None
    body_ph = None

    for ph in slide.placeholders:
        try:
            ph_type = int(ph.placeholder_format.type)
        except Exception:
            ph_type = 0

        if ph_type in _SYSTEM_TYPES:
            continue
        if ph_type in _TITLE_TYPES and title_ph is None:
            title_ph = ph
        elif ph_type in _BODY_TYPES and body_ph is None:
            body_ph = ph

    # Set title
    if title_text and title_ph and title_ph.has_text_frame:
        replace_span(title_ph, title_text)

    # Collect body content from content_blocks
    bullets: list[str] = []
    body_text_parts: list[str] = []
    image_path: str = ""

    for block in content_blocks:
        ct = block.get("content_type", "")
        if ct == "bullet_list":
            bullets.extend(block.get("bullet_points", []))
        elif ct == "text":
            t = block.get("text", "")
            if t:
                body_text_parts.append(t)
        elif ct == "title":
            # LLM sometimes repeats the title in content_blocks — honour it
            t = block.get("text", "")
            if t and title_ph and title_ph.has_text_frame:
                replace_span(title_ph, t)
        elif ct == "image":
            image_path = block.get("image_path", "")

    # Write body
    if body_ph and body_ph.has_text_frame:
        if bullets:
            set_paragraph_text(body_ph, bullets, is_bullet_list=True)
        elif body_text_parts:
            replace_span(body_ph, "\n".join(body_text_parts))

    # Handle image blocks
    if image_path:
        image_path_obj = Path(image_path)
        if image_path_obj.exists() and body_ph:
            try:
                ph_type = int(body_ph.placeholder_format.type) if body_ph.placeholder_format else 0
                if ph_type == 18:
                    insert_image_into_placeholder(body_ph, image_path_obj)
                else:
                    insert_image(
                        slide, image_path_obj,
                        left=body_ph.left / slide_width,
                        top=body_ph.top / slide_height,
                        width=body_ph.width / slide_width,
                        height=body_ph.height / slide_height,
                        slide_width_emu=slide_width,
                        slide_height_emu=slide_height,
                    )
            except Exception as e:
                logger.debug(f"Image insertion failed: {e}")

    # Speaker notes
    notes_text = slide_spec.get("speaker_notes", "")
    if notes_text:
        _set_speaker_notes(slide, notes_text)


def _set_speaker_notes(slide, notes_text: str) -> None:
    try:
        tf = slide.notes_slide.notes_text_frame
        tf.text = notes_text
    except Exception as e:
        logger.debug(f"Could not set speaker notes: {e}")


class SlideBuilder:
    def __init__(self, template_path: str | Path, template_schema: dict[str, Any]) -> None:
        self.template_path = Path(template_path)
        self.template_schema = template_schema

    def build(self, slide_plan: dict[str, Any], output_path: str | Path,
              progress_callback: Callable[[str], None] | None = None) -> Path:
        return build_presentation(
            self.template_path, slide_plan, self.template_schema, output_path, progress_callback,
        )
