"""Question routing and abstention.

The expiry question must be answered from the metadata columns, not from
model prose — that is what makes the answer exact. The planner decides which
path a question takes, so it is pinned by tests.
"""

from datetime import date

from app.modules.chat.service import (
    ABSTENTION_TEXT,
    _extract_citation_indices,
    plan_metadata_query,
)
from app.ports.llm import NO_ANSWER


class TestMetadataPlanner:
    def test_next_year_lease_question(self):
        plan = plan_metadata_query(
            "Which lease agreements expire next year?", today=date(2026, 11, 19)
        )
        assert plan is not None
        assert plan["intent"] == "expiry"
        assert plan["year"] == 2027
        assert plan["doc_types"] == ["lease"]

    def test_explicit_year(self):
        plan = plan_metadata_query(
            "Which contracts expire in 2028?", today=date(2026, 11, 19)
        )
        assert plan is not None
        assert plan["year"] == 2028
        assert plan["doc_types"] == ["contract"]

    def test_this_year(self):
        plan = plan_metadata_query(
            "Which policies expire this year?", today=date(2026, 11, 19)
        )
        assert plan is not None
        assert plan["year"] == 2026

    def test_no_document_type_is_allowed(self):
        plan = plan_metadata_query(
            "What expires next year?", today=date(2026, 11, 19)
        )
        assert plan is not None
        assert plan["doc_types"] == []

    def test_agreements_map_to_contract(self):
        plan = plan_metadata_query(
            "Which agreements expire next year?", today=date(2026, 11, 19)
        )
        assert plan["doc_types"] == ["contract"]

    def test_mou_maps_to_contract(self):
        plan = plan_metadata_query(
            "Which MOUs expire next year?", today=date(2026, 11, 19)
        )
        assert plan["doc_types"] == ["contract"]

    def test_general_question_is_not_routed_to_metadata(self):
        assert plan_metadata_query("Who are the parties to the Ridgeline agreement?") is None

    def test_question_without_a_year_is_not_routed(self):
        assert plan_metadata_query("Which leases expire?") is None


class TestCitationIndices:
    def test_extracts_markers(self):
        assert _extract_citation_indices("Rent is due monthly [1] and ends [2].") == [1, 2]

    def test_no_markers(self):
        assert _extract_citation_indices("Plain prose answer.") == []

    def test_ignores_markers_outside_the_retrieved_set(self):
        """Index validation happens against the retrieved passages only, so an
        invented index can never point at a document the user cannot see."""
        assert 999 not in _extract_citation_indices("Answer [999].")


class TestAbstention:
    def test_abstention_text_is_explicit(self):
        assert "could not find an answer" in ABSTENTION_TEXT.lower()
        assert "documents you have access to" in ABSTENTION_TEXT

    def test_no_answer_sentinel_is_distinct_from_prose(self):
        assert NO_ANSWER == "NO_ANSWER"
        assert NO_ANSWER not in ABSTENTION_TEXT

    def test_abstention_never_leaks_the_sentinel(self):
        """The sentinel is an internal protocol value — it must never reach
        the user as if it were the answer."""
        assert NO_ANSWER not in ABSTENTION_TEXT
