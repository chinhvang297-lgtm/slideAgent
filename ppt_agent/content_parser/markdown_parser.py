"""Markdown parser: extracts structured content from Markdown documents."""

import asyncio
import re
from pathlib import Path
from typing import Any

from ..utils import get_logger

logger = get_logger(__name__)


async def from_markdown_async(md_path: str | Path) -> dict[str, Any]:
    """Parse a Markdown file asynchronously into structured content."""
    md_path = Path(md_path)
    text = md_path.read_text(encoding="utf-8")
    return await asyncio.get_event_loop().run_in_executor(None, _parse_markdown_text, text, md_path)


def parse_markdown(md_path: str | Path) -> dict[str, Any]:
    """Parse a Markdown file synchronously into structured content."""
    md_path = Path(md_path)
    text = md_path.read_text(encoding="utf-8")
    return _parse_markdown_text(text, md_path)


def parse_markdown_text(text: str) -> dict[str, Any]:
    """Parse Markdown text string into structured content."""
    return _parse_markdown_text(text)


def _parse_markdown_text(text: str, source_path: Path | None = None) -> dict[str, Any]:
    """Core Markdown parsing logic."""
    logger.info(f"Parsing Markdown: {source_path.name if source_path else 'text'}")

    try:
        from markdown_it import MarkdownIt
        md = MarkdownIt()
        tokens = md.parse(text)
        return _parse_tokens(tokens, text)
    except ImportError:
        logger.warning("markdown-it-py not installed, using regex parser")
        return _regex_parse_markdown(text)


def _parse_tokens(tokens, raw_text: str) -> dict[str, Any]:
    """Parse markdown-it tokens into structured content."""
    sections: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None
    current_bullets: list[str] = []
    title: str | None = None
    i = 0

    while i < len(tokens):
        token = tokens[i]

        if token.type == "heading_open":
            level = int(token.tag[1])  # h1 -> 1, h2 -> 2, etc.
            # Get heading content
            heading_text = ""
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                heading_text = _strip_md_formatting(tokens[i + 1].content)
            i += 3  # Skip heading_open, inline, heading_close

            # Flush bullets
            if current_bullets and current_section:
                current_section["content"].append({
                    "type": "bullet_list",
                    "items": current_bullets[:],
                })
                current_bullets = []

            if level == 1 and not title:
                title = heading_text
                current_section = {"title": heading_text, "content": [], "level": level}
            elif level <= 2:
                if current_section:
                    sections.append(current_section)
                current_section = {"title": heading_text, "content": [], "level": level}
            else:
                if current_section:
                    current_section["content"].append({
                        "type": "subheading",
                        "text": heading_text,
                    })
            continue

        elif token.type == "paragraph_open":
            para_text = ""
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                para_text = _strip_md_formatting(tokens[i + 1].content)
            i += 3  # Skip paragraph_open, inline, paragraph_close

            if current_bullets:
                target = current_section or {"title": "Introduction", "content": [], "level": 1}
                target["content"].append({"type": "bullet_list", "items": current_bullets[:]})
                current_bullets = []

            if para_text:
                if current_section:
                    current_section["content"].append({"type": "text", "text": para_text})
                else:
                    current_section = {
                        "title": "Introduction",
                        "content": [{"type": "text", "text": para_text}],
                        "level": 1,
                    }
            continue

        elif token.type == "bullet_list_open" or token.type == "ordered_list_open":
            # Collect all list items
            depth = 1
            i += 1
            while i < len(tokens) and depth > 0:
                t = tokens[i]
                if t.type in ("bullet_list_open", "ordered_list_open"):
                    depth += 1
                elif t.type in ("bullet_list_close", "ordered_list_close"):
                    depth -= 1
                elif t.type == "inline" and depth == 1:
                    item_text = _strip_md_formatting(t.content)
                    if item_text:
                        current_bullets.append(item_text)
                i += 1
            continue

        elif token.type == "fence":
            # Code block
            if current_section:
                current_section["content"].append({
                    "type": "code",
                    "text": token.content.strip(),
                    "language": token.info.strip() if token.info else "",
                })
            i += 1
            continue

        elif token.type == "hr":
            i += 1
            continue

        elif token.type == "html_block":
            i += 1
            continue

        else:
            i += 1

    # Flush remaining
    if current_bullets and current_section:
        current_section["content"].append({
            "type": "bullet_list",
            "items": current_bullets,
        })

    if current_section:
        sections.append(current_section)

    # Extract images from raw markdown
    images = _extract_md_images(raw_text)

    return {
        "title": title or (sections[0]["title"] if sections else "Untitled"),
        "sections": sections,
        "images": images,
        "source_type": "markdown",
    }


def _strip_md_formatting(text: str) -> str:
    """Remove inline Markdown formatting."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text.strip()


def _extract_md_images(text: str) -> list[dict[str, str]]:
    """Extract image references from Markdown."""
    pattern = r"!\[([^\]]*)\]\(([^)]+)\)"
    images = []
    for match in re.finditer(pattern, text):
        images.append({"alt": match.group(1), "path": match.group(2)})
    return images


def _regex_parse_markdown(text: str) -> dict[str, Any]:
    """Simple regex-based Markdown parser as fallback."""
    lines = text.split("\n")
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    title: str | None = None
    current_bullets: list[str] = []

    for line in lines:
        # Headings
        h_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if h_match:
            level = len(h_match.group(1))
            heading_text = h_match.group(2).strip()

            if current_bullets and current:
                current["content"].append({"type": "bullet_list", "items": current_bullets[:]})
                current_bullets = []

            if level == 1 and not title:
                title = heading_text

            if level <= 2:
                if current:
                    sections.append(current)
                current = {"title": heading_text, "content": [], "level": level}
            elif current:
                current["content"].append({"type": "subheading", "text": heading_text})
            continue

        # Bullet items
        bullet_match = re.match(r"^[\s]*[-*+]\s+(.+)$", line)
        if bullet_match:
            current_bullets.append(bullet_match.group(1).strip())
            continue

        # Ordered list
        ol_match = re.match(r"^[\s]*\d+\.\s+(.+)$", line)
        if ol_match:
            current_bullets.append(ol_match.group(1).strip())
            continue

        # Empty line: flush bullets
        if not line.strip():
            if current_bullets and current:
                current["content"].append({"type": "bullet_list", "items": current_bullets[:]})
                current_bullets = []
            continue

        # Regular paragraph
        stripped = line.strip()
        if stripped:
            if current_bullets:
                if current:
                    current["content"].append({"type": "bullet_list", "items": current_bullets[:]})
                current_bullets = []

            if current:
                # Append to last text block or create new one
                if current["content"] and current["content"][-1]["type"] == "text":
                    current["content"][-1]["text"] += " " + stripped
                else:
                    current["content"].append({"type": "text", "text": stripped})
            else:
                current = {
                    "title": "Introduction",
                    "content": [{"type": "text", "text": stripped}],
                    "level": 1,
                }

    # Flush remaining
    if current_bullets and current:
        current["content"].append({"type": "bullet_list", "items": current_bullets})
    if current:
        sections.append(current)

    images = _extract_md_images(text)
    return {
        "title": title or (sections[0]["title"] if sections else "Untitled"),
        "sections": sections,
        "images": images,
        "source_type": "markdown",
    }
