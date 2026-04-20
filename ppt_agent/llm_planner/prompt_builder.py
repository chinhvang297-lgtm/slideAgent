"""Prompt builder: constructs prompts for the LLM slide planner."""

import json
from typing import Any

SYSTEM_PROMPT = """You are an expert presentation designer with deep knowledge of visual communication and information architecture. Your task is to create professional PowerPoint presentations from document content using provided template layouts.

You will receive:
1. A template schema describing available slide layouts and their placeholders
2. Structured content to present (from PDF or Markdown)

Your responsibilities:
- Map content sections to the most appropriate template layout
- Distribute content logically across slides (avoid overcrowding)
- Maintain narrative flow and logical progression
- Respect placeholder types (title, body, image, etc.)
- Generate concise, presentation-ready text (not prose — use bullet points where appropriate)
- Suggest where images should appear when available

Guidelines:
- Title slides: Use only for the very first slide
- Section headers: Use to separate major topics
- Content slides: 3-5 bullet points maximum per slide
- Image slides: Use when the content section has associated images
- Never exceed 120 words of text per slide
- Prefer multiple focused slides over one overcrowded slide"""

CREATE_SLIDE_PLAN_TOOL = {
    "name": "create_slide_plan",
    "description": (
        "Create a detailed, complete plan for the PowerPoint presentation. "
        "Call this tool ONCE with the full plan for all slides."
    ),
    "input_schema": {
        "type": "object",
        "required": ["slides"],
        "properties": {
            "slides": {
                "type": "array",
                "description": "Complete list of slides in order",
                "items": {
                    "type": "object",
                    "required": ["slide_number", "layout_group_id", "title"],
                    "properties": {
                        "slide_number": {
                            "type": "integer",
                            "description": "1-based slide number in the output presentation",
                        },
                        "layout_group_id": {
                            "type": "integer",
                            "description": "ID of the template layout group to use for this slide",
                        },
                        "title": {
                            "type": "string",
                            "description": "Slide title text",
                        },
                        "content_blocks": {
                            "type": "array",
                            "description": "Content to place in each placeholder",
                            "items": {
                                "type": "object",
                                "required": ["placeholder_idx", "content_type"],
                                "properties": {
                                    "placeholder_idx": {
                                        "type": "integer",
                                        "description": "Index (idx) of the placeholder to fill",
                                    },
                                    "content_type": {
                                        "type": "string",
                                        "enum": ["title", "text", "bullet_list", "image"],
                                        "description": "Type of content for this placeholder",
                                    },
                                    "text": {
                                        "type": "string",
                                        "description": "Text content (for title/text types)",
                                    },
                                    "bullet_points": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Bullet point items (for bullet_list type)",
                                    },
                                    "image_path": {
                                        "type": "string",
                                        "description": "Path to image file (for image type)",
                                    },
                                },
                            },
                        },
                        "speaker_notes": {
                            "type": "string",
                            "description": "Optional speaker notes for this slide",
                        },
                    },
                },
            },
        },
    },
}


def build_planning_prompt(
    template_schema: dict[str, Any],
    structured_content: dict[str, Any],
) -> tuple[str, str]:
    """
    Build the user message for the LLM planner.

    Returns:
        Tuple of (template_description, content_description) to be passed
        as separate message blocks with different cache_control settings.
    """
    template_desc = _format_template_schema(template_schema)
    content_desc = _format_structured_content(structured_content)
    return template_desc, content_desc


def _format_template_schema(schema: dict[str, Any]) -> str:
    """Format template schema as a concise description for the LLM."""
    lines = [
        "## TEMPLATE SCHEMA",
        f"Template: {schema.get('slide_count', 0)} slides",
        f"Dimensions: {schema.get('slide_dimensions', {}).get('width_pt', 960)}pt × {schema.get('slide_dimensions', {}).get('height_pt', 540)}pt",
        "",
        "### Available Layout Groups:",
    ]

    for group in schema.get("layout_groups", []):
        lines.append(f"\n**Layout Group {group['group_id']}: {group['layout_type']}**")
        lines.append(f"  Description: {group.get('description', '')}")
        lines.append(f"  Used in slides: {group.get('slide_indices', [])}")
        lines.append("  Placeholders:")
        for ph in group.get("placeholders", []):
            pos = ph.get("position", {})
            lines.append(
                f"    - idx={ph['idx']} type={ph['type']} "
                f"at ({pos.get('left', 0):.2f}, {pos.get('top', 0):.2f}) "
                f"size {pos.get('width', 0):.2f}×{pos.get('height', 0):.2f}"
            )

    color_scheme = schema.get("color_scheme", {})
    font_scheme = schema.get("font_scheme", {})
    lines.append(f"\nColor scheme: primary={color_scheme.get('primary')}, secondary={color_scheme.get('secondary')}")
    lines.append(f"Font scheme: heading={font_scheme.get('heading')}, body={font_scheme.get('body')}")

    return "\n".join(lines)


def _format_structured_content(content: dict[str, Any]) -> str:
    """Format structured content as a concise description for the LLM."""
    lines = [
        "## CONTENT TO PRESENT",
        f"Document Title: {content.get('title', 'Untitled')}",
        f"Source: {content.get('source_type', 'unknown')}",
        f"Total sections: {len(content.get('sections', []))}",
        "",
        "### Sections:",
    ]

    for i, section in enumerate(content.get("sections", [])):
        lines.append(f"\n**Section {i + 1}: {section.get('title', '')}**")
        for item in section.get("content", [])[:5]:  # Limit preview
            item_type = item.get("type", "")
            if item_type == "text":
                text = item.get("text", "")[:200]
                lines.append(f"  [Text] {text}{'...' if len(item.get('text', '')) > 200 else ''}")
            elif item_type == "bullet_list":
                items = item.get("items", [])[:5]
                for bullet in items:
                    lines.append(f"  • {bullet}")
                if len(item.get("items", [])) > 5:
                    lines.append(f"  ... ({len(item.get('items', []))} total bullets)")
            elif item_type == "image":
                lines.append(f"  [Image] {item.get('path', '')}")
            elif item_type == "subheading":
                lines.append(f"  [Subheading] {item.get('text', '')}")

        linked_images = section.get("linked_images", [])
        if linked_images:
            lines.append(f"  [Has {len(linked_images)} linked image(s)]")

    # Include ALL content as JSON for precise planning
    lines.append("\n### Full Content (JSON):")
    # Truncate to avoid huge context
    content_for_llm = _truncate_content(content)
    lines.append(json.dumps(content_for_llm, ensure_ascii=False, indent=2))

    return "\n".join(lines)


def _truncate_content(content: dict[str, Any], max_chars: int = 30000) -> dict[str, Any]:
    """Truncate content to fit within LLM context."""
    import copy
    content_copy = copy.deepcopy(content)

    # Truncate long text blocks
    for section in content_copy.get("sections", []):
        for item in section.get("content", []):
            if item.get("type") == "text" and len(item.get("text", "")) > 500:
                item["text"] = item["text"][:500] + "..."
            elif item.get("type") == "bullet_list":
                item["items"] = item["items"][:10]

    # Check total size and truncate sections if needed
    serialized = json.dumps(content_copy, ensure_ascii=False)
    if len(serialized) > max_chars:
        # Keep first N sections
        sections = content_copy.get("sections", [])
        while len(json.dumps(content_copy, ensure_ascii=False)) > max_chars and sections:
            sections.pop()
        content_copy["sections"] = sections
        content_copy["_truncated"] = True

    return content_copy
