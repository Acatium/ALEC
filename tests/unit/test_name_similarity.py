"""Tests for string similarity utilities used in entity resolution."""

from __future__ import annotations

import pytest

from alec.knowledge.name_similarity import (
    containment_ratio,
    name_similarity_score,
    normalize_entity_name,
    token_jaccard,
)

# ---------------------------------------------------------------------------
# normalize_entity_name
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_lowercase(self):
        assert normalize_entity_name("BCBS 239") == "bcbs 239"

    def test_strip_punctuation(self):
        assert normalize_entity_name("Data Lineage (Concept)") == "data lineage concept"

    def test_strip_colons_dashes(self):
        assert normalize_entity_name("Principle: Risk Management") == "principle risk management"
        assert normalize_entity_name("BCBS-239") == "bcbs 239"

    def test_collapse_whitespace(self):
        assert normalize_entity_name("  foo   bar  ") == "foo bar"

    def test_empty(self):
        assert normalize_entity_name("") == ""

    def test_quotes_and_slashes(self):
        assert normalize_entity_name('"Traffic Signal"') == "traffic signal"
        assert normalize_entity_name("Risk/Data") == "risk data"


# ---------------------------------------------------------------------------
# token_jaccard
# ---------------------------------------------------------------------------


class TestTokenJaccard:
    def test_identical(self):
        assert token_jaccard("BCBS 239", "BCBS 239") == 1.0

    def test_completely_different(self):
        assert token_jaccard("Apple", "Banana") == 0.0

    def test_partial_overlap(self):
        # "bcbs 239" vs "bcbs 239 data" -> intersection={bcbs,239}, union={bcbs,239,data}
        assert token_jaccard("BCBS 239", "BCBS 239 Data") == pytest.approx(2 / 3)

    def test_real_duplicate_principle(self):
        # From BCBS engagement: "Principle 1" vs "Principle 1: Risk Management"
        score = token_jaccard("Principle 1", "Principle 1: Risk Management")
        # tokens: {principle,1} vs {principle,1,risk,management} -> 2/4 = 0.5
        assert score == pytest.approx(0.5)

    def test_case_insensitive(self):
        assert token_jaccard("data lineage", "Data Lineage") == 1.0

    def test_empty(self):
        assert token_jaccard("", "foo") == 0.0
        assert token_jaccard("", "") == 0.0


# ---------------------------------------------------------------------------
# containment_ratio
# ---------------------------------------------------------------------------


class TestContainment:
    def test_full_containment(self):
        # "bcbs 239" is fully contained in "bcbs 239 compliance framework"
        assert containment_ratio("BCBS 239", "BCBS 239 Compliance Framework") == 1.0

    def test_no_containment(self):
        assert containment_ratio("Apple", "Banana") == 0.0

    def test_partial_containment(self):
        # "principle 1 risk" in "principle 1 risk management"
        # shorter={principle,1,risk}, longer={principle,1,risk,management}
        # all 3 of shorter in longer -> 3/3 = 1.0
        assert containment_ratio("Principle 1 Risk", "Principle 1: Risk Management") == 1.0

    def test_shorter_is_second(self):
        # Should pick the shorter name regardless of argument order
        assert containment_ratio(
            "BCBS 239 Compliance Framework", "BCBS 239"
        ) == 1.0

    def test_empty(self):
        assert containment_ratio("", "foo") == 0.0

    def test_real_traffic_signal(self):
        # "traffic signal" vs "traffic light invention"
        # shorter={traffic,signal}, longer={traffic,light,invention}
        # overlap = {traffic} -> 1/2 = 0.5
        assert containment_ratio("Traffic Signal", "Traffic Light Invention") == 0.5


# ---------------------------------------------------------------------------
# name_similarity_score
# ---------------------------------------------------------------------------


class TestNameSimilarityScore:
    def test_exact_match_scores_1(self):
        assert name_similarity_score("BCBS 239", [], "BCBS 239") == 1.0

    def test_variant_via_aliases(self):
        score = name_similarity_score(
            "BCBS 239",
            ["Basel Committee Standard 239"],
            "Basel Committee Standard 239",
        )
        assert score == 1.0

    def test_partial_match(self):
        score = name_similarity_score(
            "Principle 1: Data Governance",
            [],
            "Principle 1",
        )
        # containment_ratio * 0.9 since "principle 1" fully contained
        # containment = 1.0 * 0.9 = 0.9, jaccard = 2/4 = 0.5
        assert score >= 0.70

    def test_no_match(self):
        score = name_similarity_score("Apple Inc.", [], "Banana Corp.")
        assert score < 0.30

    def test_bcbs_duplicates(self):
        """Real case: BCBS 239 appearing as multiple variants."""
        score = name_similarity_score(
            "BCBS 239",
            ["Basel Committee Standard 239"],
            "BCBS-239 Compliance",
        )
        # "bcbs 239" vs "bcbs 239 compliance" -> jaccard 2/3, containment 1.0*0.9
        assert score >= 0.70

    def test_data_lineage_variants(self):
        """Real case: Data Lineage vs Data Lineage (concept)."""
        score = name_similarity_score(
            "Data Lineage",
            [],
            "Data Lineage (Concept)",
        )
        # After normalization: {data, lineage} vs {data, lineage, concept}
        # containment = 1.0 * 0.9 = 0.9
        assert score >= 0.70
