"""
Main pipeline orchestrator: coordinates template analysis, content parsing,
LLM planning, and slide generation end-to-end.
"""

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config import config
from .utils import get_logger, save_json, ensure_dir, get_unique_path
from .template_analyzer import parse_template, collect_images, ppt_to_images_async
from .content_parser import parse_pdf, from_markdown_async, link_medias
from .llm_planner import plan_slides_async, SelfCorrector
from .edit_engine import build_presentation

logger = get_logger(__name__)


@dataclass
class PipelineResult:
    success: bool
    output_path: Path | None = None
    template_schema: dict[str, Any] = field(default_factory=dict)
    structured_content: dict[str, Any] = field(default_factory=dict)
    slide_plan: dict[str, Any] = field(default_factory=dict)
    validation_report: Any = None
    elapsed_seconds: float = 0.0
    error: str | None = None

    def summary(self) -> str:
        if not self.success:
            return f"❌ Failed: {self.error}"
        slides = len(self.slide_plan.get("slides", []))
        return (
            f"✓ Generated {slides} slides in {self.elapsed_seconds:.1f}s\n"
            f"  Output: {self.output_path}"
        )


class PPTAgentPipeline:
    """End-to-end pipeline for PPT generation."""

    def __init__(
        self,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.progress_callback = progress_callback or (lambda msg: logger.info(msg))
        config.ensure_dirs()

    def run(
        self,
        template_path: str | Path,
        content_path: str | Path,
        output_path: str | Path | None = None,
    ) -> PipelineResult:
        """Run the full pipeline synchronously."""
        return asyncio.run(self.run_async(template_path, content_path, output_path))

    async def run_async(
        self,
        template_path: str | Path,
        content_path: str | Path,
        output_path: str | Path | None = None,
    ) -> PipelineResult:
        """Run the full pipeline asynchronously."""
        start_time = time.monotonic()
        template_path = Path(template_path)
        content_path = Path(content_path)

        if output_path is None:
            stem = content_path.stem
            output_path = get_unique_path(config.OUTPUT_DIR / f"{stem}_generated.pptx")
        else:
            output_path = Path(output_path)

        try:
            config.validate()
        except ValueError as e:
            return PipelineResult(success=False, error=str(e))

        # --- Stage 1: Parallel template analysis + content parsing ---
        self.progress_callback("Stage 1/4: Analyzing template and parsing content...")

        try:
            template_schema, structured_content = await asyncio.gather(
                self._analyze_template(template_path),
                self._parse_content(content_path),
            )
        except Exception as e:
            logger.exception("Failed in parsing stage")
            return PipelineResult(
                success=False,
                error=f"Parsing error: {e}",
                elapsed_seconds=time.monotonic() - start_time,
            )

        # --- Stage 2: Link media ---
        self.progress_callback("Stage 2/4: Linking media resources...")
        try:
            structured_content = link_medias(
                structured_content,
                media_dir=content_path.parent,
            )
        except Exception as e:
            logger.warning(f"Media linking failed (non-critical): {e}")

        # Save intermediate results for debugging
        save_json(template_schema, config.TEMP_DIR / "template_schema.json")
        save_json(structured_content, config.TEMP_DIR / "structured_content.json")

        # --- Stage 3: LLM planning ---
        self.progress_callback("Stage 3/4: Generating slide plan with Claude...")
        try:
            slide_plan = await plan_slides_async(
                template_schema,
                structured_content,
                progress_callback=self.progress_callback,
            )
        except Exception as e:
            logger.exception("Failed in LLM planning stage")
            return PipelineResult(
                success=False,
                error=f"LLM planning error: {e}",
                template_schema=template_schema,
                structured_content=structured_content,
                elapsed_seconds=time.monotonic() - start_time,
            )

        # Apply self-correction
        corrector = SelfCorrector()
        slide_plan = corrector.validate_and_fix_plan(slide_plan, template_schema)
        save_json(slide_plan, config.TEMP_DIR / "slide_plan.json")

        # --- Stage 4: Build presentation ---
        self.progress_callback("Stage 4/4: Building presentation...")
        try:
            output = build_presentation(
                template_path=template_path,
                slide_plan=slide_plan,
                template_schema=template_schema,
                output_path=output_path,
                progress_callback=self.progress_callback,
            )
        except Exception as e:
            logger.exception("Failed in build stage")
            return PipelineResult(
                success=False,
                error=f"Build error: {e}",
                template_schema=template_schema,
                structured_content=structured_content,
                slide_plan=slide_plan,
                elapsed_seconds=time.monotonic() - start_time,
            )

        elapsed = time.monotonic() - start_time
        self.progress_callback(f"Done! Generated {len(slide_plan.get('slides', []))} slides in {elapsed:.1f}s")

        return PipelineResult(
            success=True,
            output_path=output,
            template_schema=template_schema,
            structured_content=structured_content,
            slide_plan=slide_plan,
            validation_report=corrector.report,
            elapsed_seconds=elapsed,
        )

    async def _analyze_template(self, template_path: Path) -> dict[str, Any]:
        """Analyze PPT template (runs in executor for CPU-bound work)."""
        loop = asyncio.get_event_loop()
        schema = await loop.run_in_executor(None, parse_template, template_path)
        self.progress_callback(
            f"  Template: {schema['slide_count']} slides, "
            f"{len(schema['layout_groups'])} layout groups"
        )
        return schema

    async def _parse_content(self, content_path: Path) -> dict[str, Any]:
        """Parse content file based on extension."""
        ext = content_path.suffix.lower()
        if ext == ".pdf":
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(None, parse_pdf, content_path)
        elif ext in (".md", ".markdown", ".txt"):
            content = await from_markdown_async(content_path)
        else:
            raise ValueError(f"Unsupported content format: {ext} (use .pdf, .md, or .txt)")

        sections = content.get("sections", [])
        self.progress_callback(
            f"  Content: '{content.get('title', 'Untitled')}', "
            f"{len(sections)} sections"
        )
        return content


def run_pipeline(
    template_path: str | Path,
    content_path: str | Path,
    output_path: str | Path | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> PipelineResult:
    """Convenience function to run the full pipeline."""
    pipeline = PPTAgentPipeline(progress_callback=progress_callback)
    return pipeline.run(template_path, content_path, output_path)
