"""
Layout planner: uses Claude (claude-opus-4-7) with tool use and prompt caching
to generate a slide plan from template schema and structured content.
"""

import asyncio
import json
from typing import Any

import anthropic

from ..config import config
from ..utils import get_logger
from .prompt_builder import (
    SYSTEM_PROMPT,
    CREATE_SLIDE_PLAN_TOOL,
    build_planning_prompt,
)

logger = get_logger(__name__)


def plan_slides(
    template_schema: dict[str, Any],
    structured_content: dict[str, Any],
    progress_callback=None,
) -> dict[str, Any]:
    """Synchronous wrapper for plan_slides_async."""
    return asyncio.run(plan_slides_async(template_schema, structured_content, progress_callback))


async def plan_slides_async(
    template_schema: dict[str, Any],
    structured_content: dict[str, Any],
    progress_callback=None,
) -> dict[str, Any]:
    """
    Use Claude with tool use to plan the slide layout.

    Uses prompt caching:
    - System prompt is cached (stable across requests for same template type)
    - Template schema is cached (stable for same template)
    - Content is NOT cached (varies per request)

    Returns:
        dict with 'slides' key containing list of slide plans
    """
    config.validate()

    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    template_desc, content_desc = build_planning_prompt(template_schema, structured_content)

    logger.info(f"Planning slides with model: {config.MODEL}")
    if progress_callback:
        progress_callback("Sending to Claude for slide planning...")

    # Build messages with prompt caching:
    # - Template description gets cache_control (stable per template)
    # - Content description does NOT (changes per document)
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": template_desc,
                    "cache_control": {"type": "ephemeral"},  # Cache template schema
                },
                {
                    "type": "text",
                    "text": (
                        f"Now create a slide plan for this content:\n\n{content_desc}\n\n"
                        f"Maximum slides: {config.MAX_SLIDES}. "
                        "Call the create_slide_plan tool with your complete plan."
                    ),
                },
            ],
        }
    ]

    response = await client.messages.create(
        model=config.MODEL,
        max_tokens=config.MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},  # Cache stable system prompt
            }
        ],
        tools=[CREATE_SLIDE_PLAN_TOOL],
        tool_choice={"type": "tool", "name": "create_slide_plan"},
        messages=messages,
    )

    # Log cache usage
    usage = response.usage
    logger.info(
        f"Tokens: input={usage.input_tokens}, output={usage.output_tokens}, "
        f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)}, "
        f"cache_write={getattr(usage, 'cache_creation_input_tokens', 0)}"
    )

    # Extract tool use result
    slide_plan = _extract_slide_plan(response)

    # Validate and normalize the plan
    slide_plan = _normalize_slide_plan(slide_plan, template_schema)

    if progress_callback:
        progress_callback(f"Plan created: {len(slide_plan.get('slides', []))} slides")

    logger.info(f"Slide plan created: {len(slide_plan.get('slides', []))} slides")
    return slide_plan


def _extract_slide_plan(response: anthropic.types.Message) -> dict[str, Any]:
    """Extract the slide plan from the Claude tool use response."""
    for block in response.content:
        if block.type == "tool_use" and block.name == "create_slide_plan":
            return block.input

    # If no tool use block found, try to parse text response
    for block in response.content:
        if block.type == "text":
            try:
                # Try to extract JSON from text
                text = block.text
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    logger.warning("No tool_use block found in response, returning empty plan")
    return {"slides": []}


def _normalize_slide_plan(
    plan: dict[str, Any],
    template_schema: dict[str, Any],
) -> dict[str, Any]:
    """Validate and normalize the slide plan against the template schema."""
    slides = plan.get("slides", [])
    layout_groups = {g["group_id"]: g for g in template_schema.get("layout_groups", [])}

    if not layout_groups:
        logger.warning("No layout groups in template schema")
        return plan

    # Default layout: first group
    default_group_id = next(iter(layout_groups))

    normalized_slides = []
    for i, slide in enumerate(slides):
        # Ensure required fields
        slide.setdefault("slide_number", i + 1)
        slide.setdefault("title", f"Slide {i + 1}")
        slide.setdefault("content_blocks", [])
        slide.setdefault("speaker_notes", "")

        # Validate layout_group_id
        group_id = slide.get("layout_group_id", default_group_id)
        if group_id not in layout_groups:
            logger.debug(f"Slide {i+1}: invalid layout_group_id {group_id}, using default")
            group_id = default_group_id
        slide["layout_group_id"] = group_id

        # Validate placeholder indices
        valid_phs = {ph["idx"] for ph in layout_groups[group_id].get("placeholders", [])}
        validated_blocks = []
        for block in slide.get("content_blocks", []):
            ph_idx = block.get("placeholder_idx", 0)
            if ph_idx not in valid_phs and valid_phs:
                # Use first available placeholder
                ph_idx = min(valid_phs)
                block["placeholder_idx"] = ph_idx
            validated_blocks.append(block)

        slide["content_blocks"] = validated_blocks
        normalized_slides.append(slide)

    return {"slides": normalized_slides}
