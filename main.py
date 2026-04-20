#!/usr/bin/env python3
"""PPTAgent CLI - Generate presentations from templates and content."""

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ppt-agent",
        description="PPTAgent: Intelligent Presentation Auto-Generation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py template.pptx report.pdf
  python main.py template.pptx content.md -o output.pptx
  python main.py template.pptx content.pdf -o presentation.pptx --verbose
""",
    )
    parser.add_argument("template", help="Path to PPT template file (.pptx)")
    parser.add_argument("content", help="Path to content file (.pdf, .md, or .txt)")
    parser.add_argument("-o", "--output", help="Output path for generated PPTX", default=None)
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument(
        "--model",
        default=None,
        help="Claude model to use (default: claude-opus-4-7)",
    )
    parser.add_argument(
        "--save-plan",
        action="store_true",
        help="Save the slide plan JSON to temp directory",
    )

    args = parser.parse_args()

    # Validate inputs
    template_path = Path(args.template)
    content_path = Path(args.content)

    if not template_path.exists():
        print(f"Error: Template file not found: {template_path}", file=sys.stderr)
        return 1

    if not template_path.suffix.lower() == ".pptx":
        print(f"Error: Template must be a .pptx file: {template_path}", file=sys.stderr)
        return 1

    if not content_path.exists():
        print(f"Error: Content file not found: {content_path}", file=sys.stderr)
        return 1

    # Override model if specified
    if args.model:
        from ppt_agent.config import config
        config.MODEL = args.model

    # Set up progress callback
    def progress(msg: str) -> None:
        print(f"  {msg}")

    print(f"\nPPTAgent - Generating presentation")
    print(f"  Template: {template_path}")
    print(f"  Content:  {content_path}")
    if args.output:
        print(f"  Output:   {args.output}")
    print()

    from ppt_agent.pipeline import run_pipeline

    result = run_pipeline(
        template_path=template_path,
        content_path=content_path,
        output_path=args.output,
        progress_callback=progress,
    )

    print()
    print(result.summary())

    if result.success:
        if result.validation_report:
            report = result.validation_report
            if report.issues:
                print(f"\nValidation: {report.warning_count} warnings auto-fixed")
                if args.verbose:
                    for issue in report.issues[:5]:
                        status = "✓ fixed" if issue.auto_fixed else "⚠ manual"
                        print(f"  [{status}] Slide {issue.slide_index+1}: {issue.description}")
        return 0
    else:
        print(f"\nError details: {result.error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
