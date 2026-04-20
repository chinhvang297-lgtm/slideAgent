"""PDF parser: extracts structured content from PDF documents."""

import re
from pathlib import Path
from typing import Any

from ..utils import get_logger

logger = get_logger(__name__)


def parse_pdf(pdf_path: str | Path) -> dict[str, Any]:
    """
    Parse a PDF file into structured content.

    Returns:
        dict with: title, sections, metadata, images
    """
    pdf_path = Path(pdf_path)
    logger.info(f"Parsing PDF: {pdf_path.name}")

    try:
        import pdfplumber
        return _parse_with_pdfplumber(pdf_path)
    except ImportError:
        pass

    try:
        from PyPDF2 import PdfReader
        return _parse_with_pypdf2(pdf_path, PdfReader)
    except ImportError:
        raise ImportError("Install pdfplumber or PyPDF2: pip install pdfplumber PyPDF2")


def _parse_with_pdfplumber(pdf_path: Path) -> dict[str, Any]:
    """Parse PDF using pdfplumber (better layout awareness)."""
    import pdfplumber

    sections = []
    all_text_blocks = []
    extracted_images = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        doc_title = _extract_pdf_title(pdf)
        total_pages = len(pdf.pages)

        for page_num, page in enumerate(pdf.pages):
            # Extract text with layout
            words = page.extract_words(keep_blank_chars=False, use_text_flow=True)
            page_text = page.extract_text() or ""

            # Extract images from page
            if page.images:
                for img_idx, img in enumerate(page.images):
                    extracted_images.append({
                        "page": page_num + 1,
                        "index": img_idx,
                        "bbox": [img.get("x0"), img.get("top"), img.get("x1"), img.get("bottom")],
                    })

            # Analyze text blocks for structure
            blocks = _analyze_page_text(page_text, page_num + 1, words)
            all_text_blocks.extend(blocks)

        # Build sections from blocks
        sections = _build_sections(all_text_blocks)

    result = {
        "title": doc_title or _infer_title(sections),
        "total_pages": total_pages,
        "sections": sections,
        "images": extracted_images,
        "source_type": "pdf",
    }

    logger.info(f"PDF parsed: {total_pages} pages, {len(sections)} sections")
    return result


def _extract_pdf_title(pdf) -> str | None:
    """Extract PDF title from metadata."""
    try:
        meta = pdf.metadata
        if meta and meta.get("Title"):
            return meta["Title"].strip()
    except Exception:
        pass
    return None


def _analyze_page_text(text: str, page_num: int, words: list) -> list[dict[str, Any]]:
    """Analyze page text and identify structural elements."""
    if not text:
        return []

    blocks = []
    lines = text.split("\n")

    # Estimate font sizes from word objects if available
    word_heights = {}
    for w in words:
        line_text = w.get("text", "")
        height = w.get("height", 0)
        if line_text and height:
            word_heights[line_text] = height

    current_para_lines = []
    avg_height = sum(word_heights.values()) / len(word_heights) if word_heights else 12

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_para_lines:
                blocks.append({
                    "type": "paragraph",
                    "text": " ".join(current_para_lines),
                    "page": page_num,
                })
                current_para_lines = []
            continue

        # Heading detection heuristics
        is_heading = _is_likely_heading(stripped, avg_height, word_heights)

        if is_heading:
            if current_para_lines:
                blocks.append({
                    "type": "paragraph",
                    "text": " ".join(current_para_lines),
                    "page": page_num,
                })
                current_para_lines = []
            blocks.append({
                "type": "heading",
                "text": stripped,
                "page": page_num,
                "level": _estimate_heading_level(stripped),
            })
        elif _is_bullet_item(stripped):
            if current_para_lines:
                blocks.append({
                    "type": "paragraph",
                    "text": " ".join(current_para_lines),
                    "page": page_num,
                })
                current_para_lines = []
            blocks.append({
                "type": "bullet",
                "text": _clean_bullet(stripped),
                "page": page_num,
            })
        else:
            current_para_lines.append(stripped)

    if current_para_lines:
        blocks.append({
            "type": "paragraph",
            "text": " ".join(current_para_lines),
            "page": page_num,
        })

    return blocks


def _is_likely_heading(text: str, avg_height: float, word_heights: dict) -> bool:
    """Heuristic heading detection."""
    if len(text) > 200:
        return False
    if len(text) < 3:
        return False

    # Short all-caps lines are likely headings
    if text.isupper() and 3 <= len(text) <= 80:
        return True

    # Lines ending with no punctuation and short enough
    if len(text) <= 80 and not text.endswith((".", ",", ";", ":")):
        words_in_line = text.split()
        if len(words_in_line) <= 10:
            # Check if words are capitalized (title case)
            cap_count = sum(1 for w in words_in_line if w and w[0].isupper())
            if cap_count >= len(words_in_line) * 0.6:
                return True

    # Numbered headings: "1.", "1.1", "Chapter X"
    if re.match(r"^(\d+\.?\d*\.?\s+|Chapter\s+\d+|Section\s+\d+)", text, re.IGNORECASE):
        return True

    return False


def _estimate_heading_level(text: str) -> int:
    """Estimate heading level (1=H1, 2=H2, 3=H3)."""
    if re.match(r"^Chapter\s+\d+", text, re.IGNORECASE):
        return 1
    if re.match(r"^\d+\.\s+", text):
        return 1
    if re.match(r"^\d+\.\d+\.?\s+", text):
        return 2
    if re.match(r"^\d+\.\d+\.\d+\.?\s+", text):
        return 3
    if text.isupper():
        return 1
    return 2


def _is_bullet_item(text: str) -> bool:
    """Check if text is a bullet list item."""
    return bool(re.match(r"^[•\-\*▪◦➢→►]\s+", text)) or bool(
        re.match(r"^[a-zA-Z]\)\s+|^\d+\)\s+", text)
    )


def _clean_bullet(text: str) -> str:
    """Remove bullet marker from text."""
    return re.sub(r"^[•\-\*▪◦➢→►]\s+|^[a-zA-Z]\)\s+|^\d+\)\s+", "", text).strip()


def _build_sections(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build hierarchical sections from flat text blocks."""
    sections = []
    current_section: dict[str, Any] | None = None
    current_bullets: list[str] = []

    for block in blocks:
        if block["type"] == "heading" and block.get("level", 2) <= 2:
            # Flush pending bullets
            if current_bullets and current_section:
                current_section["content"].append({
                    "type": "bullet_list",
                    "items": current_bullets[:],
                })
                current_bullets = []

            # Save previous section
            if current_section:
                sections.append(current_section)

            current_section = {
                "title": block["text"],
                "page": block["page"],
                "content": [],
            }
        elif block["type"] == "bullet":
            current_bullets.append(block["text"])
        elif block["type"] == "paragraph" and block["text"].strip():
            # Flush pending bullets first
            if current_bullets:
                target = current_section if current_section else None
                if target:
                    target["content"].append({
                        "type": "bullet_list",
                        "items": current_bullets[:],
                    })
                current_bullets = []

            if current_section:
                current_section["content"].append({
                    "type": "text",
                    "text": block["text"],
                })
            else:
                # Content before first heading goes into an intro section
                if not sections:
                    current_section = {
                        "title": "Introduction",
                        "page": block["page"],
                        "content": [{"type": "text", "text": block["text"]}],
                    }
        elif block["type"] == "heading" and block.get("level", 2) > 2:
            # Sub-heading as content
            if current_bullets:
                if current_section:
                    current_section["content"].append({
                        "type": "bullet_list",
                        "items": current_bullets[:],
                    })
                current_bullets = []
            if current_section:
                current_section["content"].append({
                    "type": "subheading",
                    "text": block["text"],
                })

    # Flush remaining bullets
    if current_bullets and current_section:
        current_section["content"].append({
            "type": "bullet_list",
            "items": current_bullets,
        })

    # Save last section
    if current_section:
        sections.append(current_section)

    return sections


def _infer_title(sections: list[dict]) -> str:
    """Infer document title from first section."""
    if sections:
        return sections[0]["title"]
    return "Untitled Document"


def _parse_with_pypdf2(pdf_path: Path, PdfReader) -> dict[str, Any]:
    """Fallback PDF parser using PyPDF2."""
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)

    all_text = ""
    for page in reader.pages:
        text = page.extract_text() or ""
        all_text += text + "\n\n"

    # Simple split into sections by double newline
    paragraphs = [p.strip() for p in all_text.split("\n\n") if p.strip()]
    sections = []
    current: dict[str, Any] | None = None

    for para in paragraphs:
        if _is_likely_heading(para, 12, {}):
            if current:
                sections.append(current)
            current = {"title": para, "page": 1, "content": []}
        elif current:
            current["content"].append({"type": "text", "text": para})
        else:
            current = {"title": "Introduction", "page": 1, "content": [{"type": "text", "text": para}]}

    if current:
        sections.append(current)

    return {
        "title": _infer_title(sections),
        "total_pages": total_pages,
        "sections": sections,
        "images": [],
        "source_type": "pdf",
    }
