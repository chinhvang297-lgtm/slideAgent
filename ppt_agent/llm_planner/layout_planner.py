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
    Use Qwen with streaming + thinking to plan the slide layout.
    """
    config.validate()

    client = AsyncOpenAI(
        api_key=config.DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    template_desc, content_desc = build_planning_prompt(template_schema, structured_content)

    logger.info(f"Planning slides with model: {config.MODEL}")
    if progress_callback:
        progress_callback(f"Stage 3: Sending to {config.MODEL} for slide planning (deep thinking)...")

    stream = await client.chat.completions.create(
        model=config.MODEL,
        max_tokens=config.MAX_TOKENS,
        tools=[{
            "type": "function",
            "function": {
                "name": CREATE_SLIDE_PLAN_TOOL["name"],
                "description": "Create a complete, unique slide plan for the presentation.",
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
                    f"Create a slide plan for this content:\n\n{content_desc}\n\n"
                    f"Maximum slides: {config.MAX_SLIDES}. "
                    "Cover ALL sections. Every slide must have unique content. "
                    "Call create_slide_plan with the complete plan."
                ),
            },
        ],
        stream=True,
        extra_body={"enable_thinking": True},
    )

    # Accumulate streamed tool call chunks
    tool_args_by_idx: dict[int, str] = {}
    content_text = ""

    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = getattr(tc, "index", 0)
                if idx not in tool_args_by_idx:
                    tool_args_by_idx[idx] = ""
                if tc.function and tc.function.arguments:
                    tool_args_by_idx[idx] += tc.function.arguments

        if delta.content:
            content_text += delta.content

    # Parse plan
    slide_plan: dict[str, Any] = {"slides": []}
    if tool_args_by_idx:
        try:
            slide_plan = json.loads(tool_args_by_idx[0])
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse tool call arguments: {e}")
            slide_plan = _extract_from_text(content_text)
    else:
        slide_plan = _extract_from_text(content_text)

    slide_plan = _normalize_slide_plan(slide_plan, template_schema)

    n = len(slide_plan.get("slides", []))
    if progress_callback:
        progress_callback(f"Plan created: {n} slides")
    logger.info(f"Slide plan created: {n} slides")
    return slide_plan


def _extract_from_text(text: str) -> dict[str, Any]:
    """Try to extract a JSON slide plan from raw text content."""
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    logger.warning("No slide plan found in response, returning empty plan")
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
            logger.debug(f"Slide {i+1}: invalid layout_group_id {group_id!r}, using default")
            group_id = default_group_id
        slide["layout_group_id"] = group_id

        valid_phs = {ph["idx"] for ph in layout_groups[group_id].get("placeholders", [])}
        validated_blocks = []
        for block in slide.get("content_blocks", []):
            ph_idx = block.get("placeholder_idx", 0)
            if ph_idx not in valid_phs and valid_phs:
                # Try to find the best matching placeholder by content type
                content_type = block.get("content_type", "text")
                if content_type == "title":
                    ph_idx = min(valid_phs)  # title is usually the lowest idx
                else:
                    # Use the second-lowest idx for body content, or min if only one
                    sorted_phs = sorted(valid_phs)
                    ph_idx = sorted_phs[1] if len(sorted_phs) > 1 else sorted_phs[0]
                block["placeholder_idx"] = ph_idx
                logger.debug(f"Slide {i+1}: remapped block to placeholder_idx={ph_idx}")
            validated_blocks.append(block)

        slide["content_blocks"] = validated_blocks
        normalized_slides.append(slide)

    return {"slides": normalized_slides}
