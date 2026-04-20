"""
Layout planner: uses Qwen (via OpenAI-compatible API) with tool use
to generate a slide plan from template schema and structured content.
"""

import asyncio
import json
from typing import Any

from openai import AsyncOpenAI

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
    Use Qwen with tool use to plan the slide layout.

    Qwen is accessed via OpenAI-compatible endpoint (DashScope).

    Returns:
        dict with 'slides' key containing list of slide plans
    """
    config.validate()

    client = AsyncOpenAI(
        api_key=config.DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    template_desc, content_desc = build_planning_prompt(template_schema, structured_content)

    logger.info(f"Planning slides with model: {config.MODEL}")
    if progress_callback:
        progress_callback(f"Sending to {config.MODEL} for slide planning...")

    response = await client.chat.completions.create(
        model=config.MODEL,
        max_tokens=config.MAX_TOKENS,
        tools=[{
            "type": "function",
            "function": {
                "name": CREATE_SLIDE_PLAN_TOOL["name"],
                "description": "Create a complete slide plan for the presentation.",
                "parameters": CREATE_SLIDE_PLAN_TOOL["input_schema"],
            },
        }],
        tool_choice={"type": "function", "function": {"name": "create_slide_plan"}},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{template_desc}\n\n"
                    f"Now create a slide plan for this content:\n\n{content_desc}\n\n"
                    f"Maximum slides: {config.MAX_SLIDES}. "
                    "Call the create_slide_plan tool with your complete plan."
                ),
            },
        ],
    )

    # Log token usage
    usage = response.usage
    if usage:
        logger.info(
            f"Tokens: input={usage.prompt_tokens}, output={usage.completion_tokens}"
        )

    # Extract tool call result
    slide_plan = _extract_slide_plan(response)
    slide_plan = _normalize_slide_plan(slide_plan, template_schema)

    if progress_callback:
        progress_callback(f"Plan created: {len(slide_plan.get('slides', []))} slides")

    logger.info(f"Slide plan created: {len(slide_plan.get('slides', []))} slides")
    return slide_plan


def _extract_slide_plan(response) -> dict[str, Any]:
    """Extract the slide plan from the Qwen tool call response."""
    msg = response.choices[0].message

    if msg.tool_calls:
        try:
            return json.loads(msg.tool_calls[0].function.arguments)
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning(f"Failed to parse tool call arguments: {e}")

    # Fallback: try to extract JSON from text content
    text = msg.content or ""
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    logger.warning("No tool_call found in response, returning empty plan")
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

    default_group_id = next(iter(layout_groups))

    normalized_slides = []
    for i, slide in enumerate(slides):
        slide.setdefault("slide_number", i + 1)
        slide.setdefault("title", f"Slide {i + 1}")
        slide.setdefault("content_blocks", [])
        slide.setdefault("speaker_notes", "")

        group_id = slide.get("layout_group_id", default_group_id)
        if group_id not in layout_groups:
            logger.debug(f"Slide {i+1}: invalid layout_group_id {group_id}, using default")
            group_id = default_group_id
        slide["layout_group_id"] = group_id

        valid_phs = {ph["idx"] for ph in layout_groups[group_id].get("placeholders", [])}
        validated_blocks = []
        for block in slide.get("content_blocks", []):
            ph_idx = block.get("placeholder_idx", 0)
            if ph_idx not in valid_phs and valid_phs:
                ph_idx = min(valid_phs)
                block["placeholder_idx"] = ph_idx
            validated_blocks.append(block)

        slide["content_blocks"] = validated_blocks
        normalized_slides.append(slide)

    return {"slides": normalized_slides}
