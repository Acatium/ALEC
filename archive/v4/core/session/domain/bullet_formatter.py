"""Bullet formatting for LLM prompts (v3).

Converts v3 bullet format (flat list with polarity) into structured
prompt sections.
"""

from typing import Any


def format_bullets_for_llm(bullets: list[dict[str, Any]]) -> str:
    """Format v3 bullets for LLM prompt injection.

    v3 format from ADVISOR:
    [{"id", "situation", "assertion", "modality", "polarity", "score"}]

    Output: Categorized by polarity -> category mapping:
    - polarity="dont" -> Constraints
    - polarity="know" -> Reference
    - polarity="do" (default) -> Solutions

    Args:
        bullets: List of bullet dicts from ADVISOR.

    Returns:
        Formatted string for prompt injection, or empty string if no bullets.
    """
    if not bullets:
        return ""

    # Group bullets by derived category
    by_category: dict[str, list[str]] = {
        "Solutions": [],
        "Constraints": [],
        "Reference": [],
    }

    for bullet in bullets:
        polarity = bullet.get("polarity", "do")
        # Get assertion, fallback to content for backward compat
        assertion = bullet.get("assertion", bullet.get("content", ""))

        if not assertion:
            continue

        # Add position marker for citation tracking
        idx = len(by_category["Solutions"]) + len(by_category["Constraints"]) + len(by_category["Reference"]) + 1

        if polarity == "dont":
            by_category["Constraints"].append(f"[{idx}] {assertion}")
        elif polarity == "know":
            by_category["Reference"].append(f"[{idx}] {assertion}")
        else:  # "do" or default
            by_category["Solutions"].append(f"[{idx}] {assertion}")

    # Build output with category codes
    lines = ["RELEVANT KNOWLEDGE:", ""]

    category_codes = {
        "Solutions": "#S",
        "Constraints": "#C",
        "Reference": "#R",
    }

    for category, items in by_category.items():
        if items:
            code = category_codes.get(category, "")
            lines.append(f"{category} ({code}):")
            for item in items:
                lines.append(f"- {item}")
            lines.append("")

    # Return empty if no actual content
    if len(lines) <= 2:
        return ""

    return "\n".join(lines).strip()


def format_bullets_compact(bullets: list[dict[str, Any]]) -> str:
    """Format bullets in compact mode (no categories).

    For shorter prompts when categories aren't needed.

    Args:
        bullets: List of bullet dicts.

    Returns:
        Compact bullet list string.
    """
    if not bullets:
        return ""

    items = []
    for i, bullet in enumerate(bullets, 1):
        assertion = bullet.get("assertion", bullet.get("content", ""))
        if assertion:
            items.append(f"[{i}] {assertion}")

    if not items:
        return ""

    return "RELEVANT KNOWLEDGE:\n" + "\n".join(f"- {item}" for item in items)


def extract_bullet_ids(bullets: list[dict[str, Any]]) -> list[str]:
    """Extract bullet IDs for tracking.

    Args:
        bullets: List of bullet dicts.

    Returns:
        List of bullet ID strings.
    """
    ids = []
    for bullet in bullets:
        bullet_id = bullet.get("id") or bullet.get("bullet_id")
        if bullet_id:
            ids.append(str(bullet_id))
    return ids
