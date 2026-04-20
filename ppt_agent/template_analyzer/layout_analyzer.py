"""Layout analyzer: groups similar slide layouts using clustering."""

from typing import Any

import numpy as np

from ..utils import get_logger

logger = get_logger(__name__)


def _slide_to_feature_vector(slide: dict[str, Any]) -> list[float]:
    """Convert a slide's placeholder layout to a feature vector for clustering."""
    features = [0.0] * 12

    placeholders = slide.get("placeholders", [])
    for ph in placeholders:
        pos = ph.get("position", {})
        ph_type = ph.get("type", "")

        if ph_type in ("title", "center_title"):
            features[0] = pos.get("left", 0)
            features[1] = pos.get("top", 0)
            features[2] = pos.get("width", 0)
            features[3] = pos.get("height", 0)
        elif ph_type in ("body", "subtitle"):
            features[4] = pos.get("left", 0)
            features[5] = pos.get("top", 0)
            features[6] = pos.get("width", 0)
            features[7] = pos.get("height", 0)
        elif ph_type in ("picture", "bitmap"):
            features[8] = pos.get("left", 0)
            features[9] = pos.get("top", 0)

    features[10] = 1.0 if slide.get("has_images") else 0.0
    features[11] = len(placeholders) / 10.0  # normalized placeholder count
    return features


def analyze_layouts(slides: list[dict[str, Any]], max_clusters: int = 6) -> list[dict[str, Any]]:
    """
    Group slides into layout clusters using K-means.

    Returns list of layout groups with representative slide indices.
    """
    if not slides:
        return []

    # Build feature matrix
    feature_vectors = [_slide_to_feature_vector(s) for s in slides]
    X = np.array(feature_vectors)

    # Determine optimal number of clusters
    n_slides = len(slides)
    n_clusters = min(max_clusters, n_slides)

    if n_clusters <= 1:
        return [_make_layout_group(0, list(range(n_slides)), slides)]

    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Find best k using inertia elbow
        best_k = _find_best_k(X_scaled, n_clusters)
        kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X_scaled)

        # Build layout groups
        groups: dict[int, list[int]] = {}
        for slide_idx, label in enumerate(labels):
            groups.setdefault(int(label), []).append(slide_idx)

        layout_groups = []
        for group_id, slide_indices in sorted(groups.items()):
            group = _make_layout_group(group_id, slide_indices, slides)
            layout_groups.append(group)

        logger.info(f"Found {len(layout_groups)} layout groups from {n_slides} slides")
        return layout_groups

    except ImportError:
        # Fallback: group by layout_type string
        return _group_by_layout_type(slides)


def _find_best_k(X: np.ndarray, max_k: int) -> int:
    """Simple elbow method to find optimal k."""
    from sklearn.cluster import KMeans

    if max_k <= 2:
        return max_k

    inertias = []
    k_range = range(1, min(max_k + 1, len(X) + 1))
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=5)
        km.fit(X)
        inertias.append(km.inertia_)

    # Find elbow: largest drop in inertia
    if len(inertias) < 3:
        return len(inertias)

    diffs = [inertias[i] - inertias[i + 1] for i in range(len(inertias) - 1)]
    best_k = diffs.index(max(diffs)) + 2  # +2 because we start from k=1
    return min(best_k, max_k)


def _make_layout_group(
    group_id: int,
    slide_indices: list[int],
    slides: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a layout group descriptor from a set of slide indices."""
    if not slide_indices:
        return {"group_id": group_id, "slide_indices": [], "layout_types": [], "representative_index": 0}

    # Find most common layout type
    layout_types = [slides[i]["layout_type"] for i in slide_indices]
    dominant_type = max(set(layout_types), key=layout_types.count)

    # Representative slide is the first one with the dominant type
    representative = next(
        (i for i in slide_indices if slides[i]["layout_type"] == dominant_type),
        slide_indices[0],
    )

    # Collect all placeholder types in this group
    all_placeholders = []
    rep_slide = slides[representative]
    for ph in rep_slide.get("placeholders", []):
        all_placeholders.append({
            "idx": ph["idx"],
            "type": ph["type"],
            "position": ph["position"],
            "font": ph.get("font", {}),
        })

    return {
        "group_id": group_id,
        "layout_type": dominant_type,
        "slide_indices": slide_indices,
        "representative_index": representative,
        "slide_count": len(slide_indices),
        "placeholders": all_placeholders,
        "description": _describe_layout(dominant_type, all_placeholders),
    }


def _describe_layout(layout_type: str, placeholders: list[dict]) -> str:
    """Generate a human-readable layout description."""
    ph_types = [p["type"] for p in placeholders]

    descriptions = {
        "title_slide": "Title slide with large centered title and subtitle",
        "section_header": "Section header with title only",
        "content": "Standard content slide with title and body text",
        "two_column": "Two-column layout with title and dual content areas",
        "image_left": "Image on left with title and text on right",
        "image_right": "Title and text on left with image on right",
        "image_only": "Full-slide image layout",
        "blank": "Blank slide with no placeholders",
    }

    base = descriptions.get(layout_type, f"Custom layout: {layout_type}")
    ph_summary = ", ".join(sorted(set(ph_types)))
    return f"{base} [placeholders: {ph_summary}]"


def _group_by_layout_type(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fallback grouping by layout type string."""
    groups: dict[str, list[int]] = {}
    for i, slide in enumerate(slides):
        lt = slide.get("layout_type", "unknown")
        groups.setdefault(lt, []).append(i)

    layout_groups = []
    for gid, (lt, indices) in enumerate(groups.items()):
        group = _make_layout_group(gid, indices, slides)
        layout_groups.append(group)

    return layout_groups
