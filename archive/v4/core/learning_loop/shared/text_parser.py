"""Text parsers for LLM responses.

LLMs produce more reliable output with natural language delimiters than JSON.
These parsers extract structured data from delimited text responses.

v4 Updates (gap-aku-001):
- Renamed bullets → AKUs in comments
- Removed modality/polarity from AKU parsing (v4 simplified schema)
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Pre-compiled UUID pattern for validation (exact match)
_UUID_VALIDATE_PATTERN = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
    r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
)


def is_valid_uuid(value: str) -> bool:
    """Check if string is a valid UUID format.

    Args:
        value: String to validate

    Returns:
        True if value matches UUID format (8-4-4-4-12 hex chars)
    """
    if not value or not isinstance(value, str):
        return False
    return bool(_UUID_VALIDATE_PATTERN.match(value))


def parse_turn_analysis(response: str) -> tuple[Optional[str], list[dict]]:
    """Parse turn analysis from delimited text format.

    Expected format:
    SITUATION: General problem description

    ---TURN 1---
    SUB_TASK: Brief description
    OUTCOME: progress|solved|stuck|error
    HELPED: id1, id2 (or "none")
    HARMED: id3 (or "none")

    Returns tuple of:
    - situation: str or None (session-level problem description)
    - turns: list of turn dicts with keys:
        - turn_number: int
        - sub_task: str
        - micro_outcome: str
        - bullets_helped: list[str] (AKU IDs that helped)
        - bullets_harmed: list[str] (AKU IDs that harmed)
    """
    # Extract situation from the top of the response (before first ---TURN)
    situation = _extract_field(response, 'SITUATION')

    # Parse turns
    turns = []
    turn_blocks = re.split(r'---TURN\s*(\d+)---', response, flags=re.IGNORECASE)

    # turn_blocks alternates: [preamble, "1", content1, "2", content2, ...]
    i = 1
    while i < len(turn_blocks) - 1:
        try:
            turn_num = int(turn_blocks[i])
            content = turn_blocks[i + 1]

            turn = _parse_turn_block(turn_num, content)
            if turn:
                turns.append(turn)
        except (ValueError, IndexError):
            pass
        i += 2

    return situation, turns


def _parse_turn_block(turn_number: int, content: str) -> Optional[dict]:
    """Parse a single turn block."""
    lines = content.strip().split('\n')

    sub_task = ""
    outcome = "progress"  # default
    helped = []
    harmed = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Stop at next turn marker or end marker
        if line.startswith('---'):
            break

        # Parse key-value pairs
        if ':' in line:
            key, _, value = line.partition(':')
            key = key.strip().upper()
            value = value.strip()

            if key == 'SUB_TASK':
                sub_task = value
            elif key == 'OUTCOME':
                outcome = value.lower()
                # Normalize to valid outcomes
                if outcome not in ('solved', 'progress', 'stuck', 'error'):
                    outcome = 'progress'
            elif key == 'HELPED':
                helped = _parse_id_list(value)
            elif key == 'HARMED':
                harmed = _parse_id_list(value)

    return {
        "turn_number": turn_number,
        "sub_task": sub_task,
        "micro_outcome": outcome,
        "bullets_helped": helped,
        "bullets_harmed": harmed,
    }


def _parse_id_list(value: str) -> list[str]:
    """Parse comma-separated list of UUIDs, handling 'none' case.

    Extracts UUIDs even when LLM adds annotations like:
    "d6aa0d04-... (agent used this for debugging)"

    Only returns valid UUIDs. Non-UUID text is logged and skipped to prevent
    invalid data from propagating to the database.

    Args:
        value: Comma-separated string of UUIDs, possibly with annotations

    Returns:
        List of valid UUID strings only
    """
    if not value or value.lower() in ('none', 'n/a', '-', 'empty', '[]'):
        return []

    # UUID pattern: 8-4-4-4-12 hex characters (for extraction from text)
    uuid_pattern = re.compile(
        r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
        r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
    )

    ids = []
    skipped = []

    for item in value.split(','):
        item = item.strip()
        if not item or item.lower() in ('none', 'n/a'):
            continue

        # Extract UUID from potentially annotated string
        match = uuid_pattern.search(item)
        if match:
            ids.append(match.group())
        elif item:
            # Track skipped non-UUID items for debugging
            # Do NOT add them as IDs - this was causing database errors
            skipped.append(item[:50])  # Truncate for logging

    # Log skipped items to help debug LLM output issues
    if skipped:
        logger.warning(
            "uuid_extraction_skipped: %d non-UUID items filtered: %s",
            len(skipped),
            skipped[:3],  # Log first 3 samples
        )

    return ids


def parse_aku(response: str) -> Optional[dict]:
    """Parse AKU from delimited text format.

    Expected format (v4 simplified - no modality/polarity):
    ---AKU---
    SITUATION: When [general problem description]
    ASSERTION: Specific actionable advice
    ---END---

    Or for no AKU: NO_AKU

    Returns dict with keys: situation, assertion
    Or None if no valid AKU found.

    Length constraints: situation ≤60 chars, assertion ≤100 chars.
    """
    # Check for explicit no-AKU
    if 'NO_AKU' in response.upper() or 'NO AKU' in response.upper():
        return None

    # Find AKU block
    aku_match = re.search(
        r'---AKU---(.+?)(?:---END---|---|\Z)',
        response,
        re.IGNORECASE | re.DOTALL
    )

    if not aku_match:
        # Try to parse without markers (fallback)
        return _parse_aku_loose(response)

    content = aku_match.group(1)
    return _parse_aku_content(content)


def _parse_aku_content(content: str) -> Optional[dict]:
    """Parse AKU fields from content block.

    v4 Simplified: Only situation and assertion, no modality/polarity.
    """
    situation = ""
    assertion = ""

    lines = content.strip().split('\n')
    current_key = None
    current_value = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if this is a new key
        if ':' in line:
            first_colon = line.index(':')
            potential_key = line[:first_colon].strip().upper()

            # v4: Only accept SITUATION and ASSERTION
            if potential_key in ('SITUATION', 'ASSERTION'):
                # Save previous key's value
                if current_key:
                    value = ' '.join(current_value).strip()
                    if current_key == 'SITUATION':
                        situation = value
                    elif current_key == 'ASSERTION':
                        assertion = value

                # Start new key
                current_key = potential_key
                current_value = [line[first_colon + 1:].strip()]
                continue

        # Continuation of current key
        if current_key:
            current_value.append(line)

    # Save last key
    if current_key:
        value = ' '.join(current_value).strip()
        if current_key == 'SITUATION':
            situation = value
        elif current_key == 'ASSERTION':
            assertion = value

    # Validate minimum content
    if len(situation) < 10 or len(assertion) < 20:
        return None

    # Validate maximum content (v4 length constraints)
    if len(situation) > 60 or len(assertion) > 100:
        logger.warning(
            "aku_exceeds_length: situation=%d, assertion=%d",
            len(situation), len(assertion)
        )
        return None

    return {
        "situation": situation,
        "assertion": assertion,
    }


def _parse_aku_loose(response: str) -> Optional[dict]:
    """Fallback parser for AKU without delimiters.

    v4 Simplified: Only situation and assertion, no modality/polarity.
    Tries to find SITUATION:, ASSERTION: anywhere in response.
    """
    situation = _extract_field(response, 'SITUATION')
    assertion = _extract_field(response, 'ASSERTION')

    if not situation or not assertion:
        return None

    # Validate minimum content
    if len(situation) < 10 or len(assertion) < 20:
        return None

    # Validate maximum content (v4 length constraints)
    if len(situation) > 60 or len(assertion) > 100:
        logger.warning(
            "aku_exceeds_length: situation=%d, assertion=%d",
            len(situation), len(assertion)
        )
        return None

    return {
        "situation": situation,
        "assertion": assertion,
    }


def _extract_field(text: str, field_name: str) -> Optional[str]:
    """Extract a field value from text.

    Stops at:
    - Next field (UPPERCASE:)
    - Turn markers (---TURN)
    - End of string
    """
    pattern = rf'{field_name}\s*:\s*(.+?)(?=\n[A-Z]+\s*:|---TURN|$)'
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return None
