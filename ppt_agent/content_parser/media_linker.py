"""Media linker: associates images and media with content sections."""

import re
from pathlib import Path
from typing import Any

from ..utils import get_logger

logger = get_logger(__name__)


def link_medias(
    structured_content: dict[str, Any],
    media_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Associate media files (images, tables) with content sections.

    Resolves relative image paths and links them to the nearest content section.
    """
    if not structured_content:
        return structured_content

    sections = structured_content.get("sections", [])
    doc_images = structured_content.get("images", [])

    # Resolve image paths
    resolved_images = _resolve_image_paths(doc_images, media_dir)

    # Link images to sections
    sections_with_media = _link_images_to_sections(sections, resolved_images)

    return {
        **structured_content,
        "sections": sections_with_media,
        "images": resolved_images,
    }


def _resolve_image_paths(
    images: list[dict[str, Any]],
    media_dir: Path | None,
) -> list[dict[str, Any]]:
    """Resolve image paths to absolute paths."""
    resolved = []
    for img in images:
        path_str = img.get("path", "")
        if not path_str:
            resolved.append(img)
            continue

        path = Path(path_str)

        # Already absolute and exists
        if path.is_absolute() and path.exists():
            resolved.append({**img, "resolved_path": str(path), "exists": True})
            continue

        # Try relative to media_dir
        if media_dir and (media_dir / path).exists():
            resolved.append({
                **img,
                "resolved_path": str(media_dir / path),
                "exists": True,
            })
            continue

        # Try relative to current directory
        if path.exists():
            resolved.append({**img, "resolved_path": str(path.resolve()), "exists": True})
            continue

        resolved.append({**img, "resolved_path": path_str, "exists": False})

    return resolved


def _link_images_to_sections(
    sections: list[dict[str, Any]],
    images: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Link images to sections based on proximity and content matching.
    Images from PDF are linked by page number; Markdown images by inline reference.
    """
    if not images:
        return sections

    updated_sections = []
    for section_idx, section in enumerate(sections):
        section_images = []

        section_page = section.get("page", 1)
        section_title_lower = section.get("title", "").lower()

        for img in images:
            img_page = img.get("page")
            img_path = img.get("path", "")
            img_alt = img.get("alt", "").lower()

            # Link PDF images by page proximity
            if img_page is not None:
                # Find which section this page belongs to
                next_section_page = sections[section_idx + 1].get("page", 999) if section_idx + 1 < len(sections) else 999
                if section_page <= img_page < next_section_page:
                    section_images.append(img)
                    continue

            # Link Markdown images by path/alt text matching section title
            if img_alt and any(word in section_title_lower for word in img_alt.split() if len(word) > 3):
                section_images.append(img)
                continue

            # Link by filename matching section title words
            if img_path:
                img_name = Path(img_path).stem.lower()
                title_words = section_title_lower.split()
                if any(word in img_name for word in title_words if len(word) > 3):
                    section_images.append(img)

        # Add images to section content
        section_content = section.get("content", [])
        for img in section_images:
            if img.get("exists", False):
                section_content.append({
                    "type": "image",
                    "path": img.get("resolved_path", img.get("path", "")),
                    "alt": img.get("alt", ""),
                    "caption": img.get("alt", ""),
                })

        updated_sections.append({
            **section,
            "content": section_content,
            "linked_images": section_images,
        })

    return updated_sections
