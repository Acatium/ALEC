"""Unit tests for bullet_formatter.py.

Test Philosophy: "All correct" - fix errors, don't alter tests unless proven inaccurate.
"""

from uuid import uuid4

from core.session.domain.bullet_formatter import (
    extract_bullet_ids,
    format_bullets_compact,
    format_bullets_for_llm,
)


class TestFormatBulletsForLlm:
    """Tests for format_bullets_for_llm function."""

    def test_empty_bullets_returns_empty_string(self):
        """Empty bullet list should return empty string."""
        result = format_bullets_for_llm([])
        assert result == ""

    def test_none_bullets_returns_empty_string(self):
        """None should be handled gracefully."""
        # Would raise TypeError without guard
        result = format_bullets_for_llm(None)  # type: ignore[arg-type]
        assert result == ""

    def test_formats_do_polarity_as_solutions(self, sample_bullets):
        """Bullets with polarity='do' should appear under Solutions."""
        bullets = [b for b in sample_bullets if b["polarity"] == "do"]

        result = format_bullets_for_llm(bullets)

        assert "Solutions (#S):" in result
        assert "offset=0" in result

    def test_formats_dont_polarity_as_constraints(self, sample_bullets):
        """Bullets with polarity='dont' should appear under Constraints."""
        bullets = [b for b in sample_bullets if b["polarity"] == "dont"]

        result = format_bullets_for_llm(bullets)

        assert "Constraints (#C):" in result
        assert "null values" in result

    def test_formats_know_polarity_as_reference(self, sample_bullets):
        """Bullets with polarity='know' should appear under Reference."""
        bullets = [b for b in sample_bullets if b["polarity"] == "know"]

        result = format_bullets_for_llm(bullets)

        assert "Reference (#R):" in result
        assert "rate limit" in result

    def test_all_categories_formatted(self, sample_bullets):
        """All three categories should appear when all polarities present."""
        result = format_bullets_for_llm(sample_bullets)

        assert "Solutions (#S):" in result
        assert "Constraints (#C):" in result
        assert "Reference (#R):" in result
        assert "RELEVANT KNOWLEDGE:" in result

    def test_includes_position_markers(self, sample_bullets):
        """Bullets should have position markers [1], [2], etc."""
        result = format_bullets_for_llm(sample_bullets)

        assert "[1]" in result
        assert "[2]" in result
        assert "[3]" in result

    def test_uses_assertion_field(self):
        """Should use 'assertion' field for content."""
        bullets = [{
            "id": str(uuid4()),
            "situation": "test situation",
            "assertion": "test assertion content",
            "polarity": "do",
        }]

        result = format_bullets_for_llm(bullets)

        assert "test assertion content" in result

    def test_fallback_to_content_field(self):
        """Should fallback to 'content' field if 'assertion' missing."""
        bullets = [{
            "id": str(uuid4()),
            "situation": "test situation",
            "content": "fallback content value",
            "polarity": "do",
        }]

        result = format_bullets_for_llm(bullets)

        assert "fallback content value" in result

    def test_default_polarity_is_do(self):
        """Missing polarity should default to 'do' (Solutions)."""
        bullets = [{
            "id": str(uuid4()),
            "assertion": "no polarity specified",
        }]

        result = format_bullets_for_llm(bullets)

        assert "Solutions (#S):" in result

    def test_skips_empty_assertions(self):
        """Bullets with empty assertion should be skipped."""
        bullets = [
            {"id": str(uuid4()), "assertion": "", "polarity": "do"},
            {"id": str(uuid4()), "assertion": "valid content", "polarity": "do"},
        ]

        result = format_bullets_for_llm(bullets)

        assert "valid content" in result
        assert result.count("[") == 1  # Only one marker


class TestFormatBulletsCompact:
    """Tests for format_bullets_compact function."""

    def test_empty_returns_empty_string(self):
        """Empty list should return empty string."""
        result = format_bullets_compact([])
        assert result == ""

    def test_formats_without_categories(self, sample_bullets):
        """Compact format should not include category headers."""
        result = format_bullets_compact(sample_bullets)

        assert "RELEVANT KNOWLEDGE:" in result
        assert "Solutions" not in result
        assert "Constraints" not in result

    def test_includes_all_bullets(self, sample_bullets):
        """All bullets should be included regardless of polarity."""
        result = format_bullets_compact(sample_bullets)

        assert "[1]" in result
        assert "[2]" in result
        assert "[3]" in result


class TestExtractBulletIds:
    """Tests for extract_bullet_ids function."""

    def test_extracts_ids_from_id_field(self):
        """Should extract from 'id' field."""
        bullets = [
            {"id": "abc-123", "assertion": "test"},
            {"id": "def-456", "assertion": "test"},
        ]

        result = extract_bullet_ids(bullets)

        assert "abc-123" in result
        assert "def-456" in result

    def test_extracts_ids_from_bullet_id_field(self):
        """Should extract from 'bullet_id' field as fallback."""
        bullets = [
            {"bullet_id": "ghi-789", "assertion": "test"},
        ]

        result = extract_bullet_ids(bullets)

        assert "ghi-789" in result

    def test_skips_missing_ids(self):
        """Should skip bullets without ID fields."""
        bullets = [
            {"id": "valid-id", "assertion": "test"},
            {"assertion": "no id"},
        ]

        result = extract_bullet_ids(bullets)

        assert len(result) == 1
        assert "valid-id" in result

    def test_converts_to_strings(self):
        """IDs should be converted to strings."""
        test_uuid = uuid4()
        bullets = [{"id": test_uuid, "assertion": "test"}]

        result = extract_bullet_ids(bullets)

        assert str(test_uuid) in result
        assert isinstance(result[0], str)
