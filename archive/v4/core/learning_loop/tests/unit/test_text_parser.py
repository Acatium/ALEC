"""Unit tests for text_parser module.

Tests UUID parsing and validation functions added in GAP-021.
"""


from core.learning_loop.shared.text_parser import (
    _parse_id_list,
    is_valid_uuid,
    parse_aku,
    parse_turn_analysis,
)


class TestIsValidUuid:
    """Tests for is_valid_uuid() helper function."""

    def test_valid_lowercase_uuid(self):
        """Standard lowercase UUID is valid."""
        assert is_valid_uuid("d6aa0d04-1234-5678-9abc-def012345678") is True

    def test_valid_uppercase_uuid(self):
        """Uppercase UUID is valid."""
        assert is_valid_uuid("D6AA0D04-1234-5678-9ABC-DEF012345678") is True

    def test_valid_mixed_case_uuid(self):
        """Mixed case UUID is valid."""
        assert is_valid_uuid("d6AA0d04-1234-5678-9AbC-DeF012345678") is True

    def test_invalid_short_uuid(self):
        """Incomplete UUID is invalid."""
        assert is_valid_uuid("d6aa0d04-1234-5678-9abc") is False

    def test_invalid_text(self):
        """Plain text is invalid."""
        assert is_valid_uuid("but agent didn't implement this)") is False

    def test_invalid_empty_string(self):
        """Empty string is invalid."""
        assert is_valid_uuid("") is False

    def test_invalid_none(self):
        """None is invalid."""
        assert is_valid_uuid(None) is False  # type: ignore

    def test_invalid_with_extra_chars(self):
        """UUID with extra characters is invalid."""
        assert is_valid_uuid("d6aa0d04-1234-5678-9abc-def012345678-extra") is False

    def test_invalid_with_annotation(self):
        """UUID with annotation (not stripped) is invalid for exact match."""
        # is_valid_uuid does exact match, not extraction
        assert is_valid_uuid("d6aa0d04-1234-5678-9abc-def012345678 (note)") is False


class TestParseIdList:
    """Tests for _parse_id_list() function - the main bug fix."""

    def test_single_valid_uuid(self):
        """Single valid UUID is extracted correctly."""
        result = _parse_id_list("d6aa0d04-1234-5678-9abc-def012345678")
        assert result == ["d6aa0d04-1234-5678-9abc-def012345678"]

    def test_multiple_valid_uuids(self):
        """Multiple comma-separated UUIDs are extracted."""
        result = _parse_id_list(
            "d6aa0d04-1234-5678-9abc-def012345678, a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        )
        assert len(result) == 2
        assert "d6aa0d04-1234-5678-9abc-def012345678" in result
        assert "a1b2c3d4-e5f6-7890-abcd-ef1234567890" in result

    def test_uuid_with_annotation(self):
        """UUID with LLM annotation is extracted correctly."""
        result = _parse_id_list(
            "d6aa0d04-1234-5678-9abc-def012345678 (agent used this for debugging)"
        )
        assert result == ["d6aa0d04-1234-5678-9abc-def012345678"]

    def test_none_keyword(self):
        """'none' returns empty list."""
        assert _parse_id_list("none") == []

    def test_na_keyword(self):
        """'n/a' returns empty list."""
        assert _parse_id_list("n/a") == []

    def test_empty_string(self):
        """Empty string returns empty list."""
        assert _parse_id_list("") == []

    def test_empty_brackets(self):
        """'[]' returns empty list."""
        assert _parse_id_list("[]") == []

    def test_dash(self):
        """'-' returns empty list."""
        assert _parse_id_list("-") == []

    def test_invalid_text_returns_empty(self):
        """GAP-021 FIX: Invalid text should return empty list, not the text."""
        result = _parse_id_list("but agent didn't follow through effectively)")
        assert result == []

    def test_another_invalid_text(self):
        """GAP-021 FIX: Another invalid text case."""
        result = _parse_id_list("but agent didn't implement this pivot)")
        assert result == []

    def test_mixed_valid_and_invalid(self):
        """GAP-021 FIX: Mixed input returns only valid UUIDs."""
        result = _parse_id_list(
            "d6aa0d04-1234-5678-9abc-def012345678, but didn't work"
        )
        assert result == ["d6aa0d04-1234-5678-9abc-def012345678"]

    def test_uuid_with_whitespace(self):
        """UUID with surrounding whitespace is extracted."""
        result = _parse_id_list("  d6aa0d04-1234-5678-9abc-def012345678  ")
        assert result == ["d6aa0d04-1234-5678-9abc-def012345678"]

    def test_uppercase_uuid(self):
        """Uppercase UUID is extracted."""
        result = _parse_id_list("D6AA0D04-1234-5678-9ABC-DEF012345678")
        assert result == ["D6AA0D04-1234-5678-9ABC-DEF012345678"]

    def test_multiple_invalid_items(self):
        """Multiple invalid items all filtered out."""
        result = _parse_id_list("bad text, more bad, still bad")
        assert result == []

    def test_valid_between_invalid(self):
        """Valid UUID between invalid items is extracted."""
        result = _parse_id_list(
            "bad, d6aa0d04-1234-5678-9abc-def012345678, also bad"
        )
        assert result == ["d6aa0d04-1234-5678-9abc-def012345678"]


class TestParseTurnAnalysis:
    """Tests for parse_turn_analysis() function."""

    def test_basic_turn_analysis(self):
        """Basic turn analysis parsing works."""
        response = """SITUATION: When testing API endpoints

---TURN 1---
SUB_TASK: Initial API call
OUTCOME: progress
HELPED: none
HARMED: none

---TURN 2---
SUB_TASK: Parse response
OUTCOME: solved
HELPED: d6aa0d04-1234-5678-9abc-def012345678
HARMED: none
"""
        situation, turns = parse_turn_analysis(response)
        assert situation == "When testing API endpoints"
        assert len(turns) == 2
        assert turns[0]["micro_outcome"] == "progress"
        assert turns[1]["micro_outcome"] == "solved"
        assert turns[1]["bullets_helped"] == ["d6aa0d04-1234-5678-9abc-def012345678"]

    def test_turn_with_invalid_helped_filtered(self):
        """GAP-021: Invalid text in HELPED field is filtered out."""
        response = """SITUATION: Test

---TURN 1---
SUB_TASK: Do thing
OUTCOME: progress
HELPED: but agent didn't follow through)
HARMED: none
"""
        situation, turns = parse_turn_analysis(response)
        assert len(turns) == 1
        # Invalid text should be filtered, not included
        assert turns[0]["bullets_helped"] == []


class TestParseAku:
    """Tests for parse_aku() function.

    v4 Simplified: AKUs only have situation and assertion (no modality/polarity).
    Length constraints: situation ≤60, assertion ≤100 chars.
    """

    def test_basic_aku_parsing(self):
        """Basic AKU parsing works (v4 format - no modality/polarity)."""
        response = """---AKU---
SITUATION: When testing API endpoints
ASSERTION: Always verify the response status code before parsing the body
---END---
"""
        aku = parse_aku(response)
        assert aku is not None
        assert aku["situation"] == "When testing API endpoints"
        assert "verify the response status code" in aku["assertion"]
        # v4: No modality/polarity
        assert "modality" not in aku
        assert "polarity" not in aku

    def test_aku_exceeds_length_constraints(self):
        """AKU exceeding length constraints returns None."""
        # Situation > 60 chars
        response = """---AKU---
SITUATION: When testing API endpoints with a very long situation description that exceeds the limit
ASSERTION: Always verify the response status code
---END---
"""
        aku = parse_aku(response)
        assert aku is None

        # Assertion > 100 chars
        response2 = """---AKU---
SITUATION: When testing API endpoints
ASSERTION: This is a very long assertion that exceeds the one hundred character limit and should be rejected by the parser
---END---
"""
        aku2 = parse_aku(response2)
        assert aku2 is None

    def test_no_aku_keyword(self):
        """NO_AKU returns None."""
        assert parse_aku("NO_AKU") is None
        assert parse_aku("No AKU found") is None
