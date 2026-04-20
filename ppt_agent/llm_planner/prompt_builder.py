"""Prompt builder: constructs prompts for the LLM slide planner."""

import json
from typing import Any

SYSTEM_PROMPT = """You are an expert PowerPoint presentation designer. Your job is to create a \
detailed, content-rich slide plan from a document using a specific template.

## ABSOLUTE RULES — NEVER VIOLATE

1. **Every slide MUST have UNIQUE content** — never repeat the same text on multiple slides
2. **Cover ALL document sections** — distribute the full document across slides
3. **Always include the title in content_blocks** — add a block with placeholder_idx=0 and \
content_type="title" on EVERY slide
4. **Use EXACT placeholder_idx values** from the template schema — do not invent new ones
5. **Fill ALL available placeholders** on each slide (at minimum: title + body)
6. **3–5 bullet points per slide** for bullet_list type — concise, presentation-ready
7. **Never exceed 120 words per slide** total

## PLACEHOLDER MAPPING RULE

- `idx=0` → title placeholder → always `content_type="title"`
- `idx=1` → main body/content placeholder → `content_type="bullet_list"` or `"text"`
- Higher `idx` → additional placeholders (captions, subtitles, etc.)

## EXAMPLE — correct slide entry

```json
{
  "slide_number": 2,
  "layout_group_id": 1,
  "title": "Q3 Revenue Growth",
  "content_blocks": [
    {"placeholder_idx": 0, "content_type": "title", "text": "Q3 Revenue Growth"},
    {"placeholder_idx": 1, "content_type": "bullet_list", "bullet_points": [
      "Revenue reached $2.4M, up 34% year-over-year",
      "Enterprise segment grew 48% this quarter",
      "3 new Fortune 500 clients onboarded"
    ]}
  ],
  "speaker_notes": "Emphasize enterprise growth as the key driver"
}
```

## SLIDE STRUCTURE GUIDE

- **Slide 1**: Title slide — presentation title + subtitle
- **Slides 2–N**: One slide per major section or sub-topic
  - Section header slides: use a simple layout for major topic transitions
  - Content slides: 3–5 bullets from that section's key points
- **Do NOT** put all content on 1–2 slides and leave others empty"""


CREATE_SLIDE_PLAN_TOOL = {
    "name": "create_slide_plan",
    "description": (
        "Create a detailed, complete plan for the PowerPoint presentation. "
        "Call this tool ONCE with the full plan for ALL slides. "
        "Every slide must have unique content from a different part of the document."
    ),
    "input_schema": {
        "type": "object",
        "required": ["slides"],
        "properties": {
            "slides": {
                "type": "array",
                "description": "Complete ordered list of slides — must cover the entire document",
                "items": {
                    "type": "object",
                    "required": ["slide_number", "layout_group_id", "title", "content_blocks"],
                    "properties": {
                        "slide_number": {
                            "type": "integer",
                            "description": "1-based slide number",
                        },
                        "layout_group_id": {
                            "type": "integer",
                            "description": "ID of the template layout group to use",
                        },
                        "title": {
                            "type": "string",
                            "description": "Slide title — must be unique per slide",
                        },
                        "content_blocks": {
                            "type": "array",
                            "description": (
                                "Content for each placeholder. MUST include idx=0 (title) "
                                "and idx=1 (body) blocks on every slide."
                            ),
                            "items": {
                                "type": "object",
                                "required": ["placeholder_idx", "content_type"],
                                "properties": {
                                    "placeholder_idx": {
                                        "type": "integer",
                                        "description": "Exact idx from template schema",
                                    },
                                    "content_type": {
                                        "type": "string",
                                        "enum": ["title", "text", "bullet_list", "image"],
                                    },
                                    "text": {
                                        "type": "string",
                                        "description": "Text for title/text types",
                                    },
                                    "bullet_points": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "3–5 bullet points for bullet_list type",
                                    },
                                    "image_path": {
                                        "type": "string",
                                        "description": "Path to image (for image type only)",
                                    },
                                },
                            },
                        },
                        "speaker_notes": {
                            "type": "string",
                            "description": "Optional speaker notes",
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
    template_desc = _format_template_schema(template_schema)
    content_desc = _format_structured_content(structured_content)
    return template_desc, content_desc


def _format_template_schema(schema: dict[str, Any]) -> str:
    lines = [
        "## TEMPLATE SCHEMA",
        f"Source template: {schema.get('slide_count', 0)} slides, "
        f"{schema.get('slide_dimensions', {}).get('width_pt', 960)}×"
        f"{schema.get('slide_dimensions', {}).get('height_pt', 540)}pt",
        "",
        "### Available Layout Groups",
        "⚠️  Use these EXACT group_id and placeholder_idx values in your plan:",
    ]

    for group in schema.get("layout_groups", []):
        lines.append(f"\n**Group {group['group_id']}: {group['layout_type']}**")
        if group.get("description"):
            lines.append(f"  Purpose: {group['description']}")
        lines.append(f"  Example slides: {group.get('slide_indices', [])}")
        lines.append("  Placeholders (use these exact idx values):")
        for ph in group.get("placeholders", []):
            ph_type = str(ph.get("type", "")).upper()
            hint = ""
            if any(t in ph_type for t in ("TITLE", "CENTER", "title", "center")):
                hint = "  ← PUT SLIDE TITLE HERE (content_type='title')"
            elif any(t in ph_type for t in ("BODY", "OBJECT", "CONTENT", "body", "object", "subtitle")):
                hint = "  ← PUT BULLETS/TEXT HERE (content_type='bullet_list' or 'text')"
            elif "PICTURE" in ph_type or "PIC" in ph_type:
                hint = "  ← PUT IMAGE HERE (content_type='image')"
            elif "SUBTITLE" in ph_type:
                hint = "  ← PUT SUBTITLE HERE (content_type='text')"
            pos = ph.get("position", {})
            lines.append(
                f"    placeholder_idx={ph['idx']}  type={ph['type']}{hint}"
                f"  (pos: {pos.get('left', 0):.0f},{pos.get('top', 0):.0f} "
                f"size: {pos.get('width', 0):.0f}×{pos.get('height', 0):.0f})"
            )

    return "\n".join(lines)


def _format_structured_content(content: dict[str, Any]) -> str:
    lines = [
        "## DOCUMENT CONTENT",
        f"Title: {content.get('title', 'Untitled')}",
        f"Sections: {len(content.get('sections', []))}",
        "",
        "### Full Content (create slides covering ALL sections below):",
    ]

    content_for_llm = _truncate_content(content)
    lines.append(json.dumps(content_for_llm, ensure_ascii=False, indent=2))

    return "\n".join(lines)


def _truncate_content(content: dict[str, Any], max_chars: int = 40000) -> dict[str, Any]:
    """Truncate content to fit within LLM context while preserving section structure."""
    import copy
    content_copy = copy.deepcopy(content)

    # First pass: truncate individual long text blocks
    for section in content_copy.get("sections", []):
        for item in section.get("content", []):
            if item.get("type") == "text" and len(item.get("text", "")) > 800:
                item["text"] = item["text"][:800] + "..."
            elif item.get("type") == "bullet_list" and len(item.get("items", [])) > 12:
                item["items"] = item["items"][:12]

    # Second pass: if still too large, truncate sections from the back
    sections = content_copy.get("sections", [])
    while len(json.dumps(content_copy, ensure_ascii=False)) > max_chars and len(sections) > 2:
        sections.pop()
        content_copy["sections"] = sections
        content_copy["_note"] = "Content truncated — plan slides for all shown sections"

    return content_copy
