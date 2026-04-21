"""Layout analyzer: groups similar slide layouts by semantic layout type."""

from typing import Any

from ..utils import get_logger

logger = get_logger(__name__)

# Layout types ordered by usefulness for content (content slides first)
_LAYOUT_PRIORITY = [
    "content", "two_column", "image_right", "image_left",
    "title_slide", "section_header", "image_only", "blank",
]


def analyze_layouts(slides: list[dict[str, Any]], max_clusters: int = 6) -> list[dict[str, Any]]:
    """
    Group slides by their semantic layout_type.

    Replaces K-means clustering which was merging section_header and content
    slides into the same group (causing orange section-header backgrounds to
    bleed into every generated content slide).
    """
    if not slides:
        return []

    # Bucket slide indices by layout_type
    buckets: dict[str, list[int]] = {}
    for i, slide in enumerate(slides):
        lt = slide.get("layout_type", "content")
        buckets.setdefault(lt, []).append(i)

    # Sort groups: content-like layouts first so group_id=0 is always usable for body slides
    ordered_types = sorted(
        buckets.keys(),
        key=lambda x: _LAYOUT_PRIORITY.index(x) if x in _LAYOUT_PRIORITY else 99,
    )

    layout_groups = []
    for gid, lt in enumerate(ordered_types):
        group = _make_layout_group(gid, buckets[lt], slides)
        layout_groups.append(group)

    logger.info(f"Found {len(layout_groups)} layout groups from {len(slides)} slides")
    for g in layout_groups:
        logger.debug(
            f"  Group {g['group_id']}: {g['layout_type']} "
            f"slides={g['slide_indices']} representative={g['representative_index']}"
        )
    return layout_groups


def _make_layout_group(
    group_id: int,
    slide_indices: list[int],
    slides: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a layout group descriptor from a set of slide indices."""
    if not slide_indices:
        return {"group_id": group_id, "slide_indices": [], "layout_type": "content", "representative_index": 0}

    layout_types = [slides[i]["layout_type"] for i in slide_indices]
    dominant_type = max(set(layout_types), key=layout_types.count)

    # Representative: first slide whose layout_type matches the dominant type
    representative = next(
        (i for i in slide_indices if slides[i]["layout_type"] == dominant_type),
        slide_indices[0],
    )

    # Collect placeholder info from the representative slide
    rep_slide = slides[representative]
    all_placeholders = [
        {
            "idx": ph["idx"],
            "type": ph["type"],
            "position": ph["position"],
            "font": ph.get("font", {}),
        }
        for ph in rep_slide.get("placeholders", [])
    ]

    return {
        "group_id": group_id,
        "layout_type": dominant_type,
        "slide_indices": slide_indices,
        "representative_index": representative,
        "slide_count": len(slide_indices),
        "placeholders": all_placeholders,
        "description": _describe_layout(dominant_type, all_placeholders),
    }


def _describe_layout(layout_type: str, placeholders: list[dict]) -> str:
    descriptions = {
        "title_slide": "Title slide with large centered title and subtitle",
        "section_header": "Section header/divider slide — use ONLY for major topic transitions",
        "content": "Standard content slide with title and body text — use for most slides",
        "two_column": "Two-column layout with title and dual content areas",
        "image_left": "Image on left with title and text on right",
        "image_right": "Title and text on left with image on right",
        "image_only": "Full-slide image layout",
        "blank": "Blank slide with no placeholders",
    }
    ph_types = [p["type"] for p in placeholders]
    base = descriptions.get(layout_type, f"Custom layout: {layout_type}")
    ph_summary = ", ".join(sorted(set(ph_types)))
    return f"{base} [placeholders: {ph_summary}]"
