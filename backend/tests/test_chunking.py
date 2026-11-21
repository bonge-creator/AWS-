"""Chunking behaviour.

Chunks are what the model is allowed to see, so their boundaries decide what
a citation can point at. These tests pin the invariants we rely on.
"""

from app.modules.ingestion.chunking import (
    MIN_CHARS,
    OVERLAP_CHARS,
    TARGET_CHARS,
    chunk_pages,
)


def pages(*items):
    return [{"page": n, "text": t} for n, t in items]


PAGES = pages(
    (
        1,
        "The parties agree to the following terms and conditions of the lease. "
        "This lease is granted for the term stated in the schedule below.",
    ),
    (
        2,
        "Rent is payable monthly in arrears on the first business day, without "
        "deduction or set-off of any kind whatsoever, and the rent shall be "
        "paid by standing order to the landlord's nominated account.",
    ),
    (
        3,
        "The tenant shall keep the premises in good repair and condition, fair "
        "wear and tear excepted, throughout the term, and shall comply with "
        "all applicable statutory obligations relating to the property.",
    ),
)


class TestChunking:
    def test_each_page_becomes_its_own_chunk(self):
        """Chunks never span a page boundary, so a citation can name a page."""
        chunks = chunk_pages(PAGES)
        assert len(chunks) == 3
        for c in chunks:
            assert c.page_start == c.page_end

    def test_pages_are_preserved(self):
        chunks = chunk_pages(PAGES)
        assert [c.page_start for c in chunks] == [1, 2, 3]
        for c in chunks:
            assert c.text.strip()

    def test_tiny_paragraph_is_dropped(self):
        """Fragments below the floor are discarded — they are noise to a model."""
        chunks = chunk_pages(pages((1, "ok.")))
        assert chunks == []

    def test_paragraph_above_floor_is_kept(self):
        body = "A" * (MIN_CHARS + 20)
        chunks = chunk_pages(pages((1, body)))
        assert len(chunks) == 1
        assert len(chunks[0].text) >= MIN_CHARS

    def test_target_and_overlap_are_sane(self):
        assert TARGET_CHARS > OVERLAP_CHARS
        assert OVERLAP_CHARS > 0

    def test_long_page_splits(self):
        long_page = pages((1, "Sentence number one here. " * 300))
        chunks = chunk_pages(long_page)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c.text) <= TARGET_CHARS * 2

    def test_chunk_indices_are_sequential(self):
        chunks = chunk_pages(pages((1, "x " * 3000)))
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_overlap_preserves_context_across_a_split(self):
        """A sentence spanning a split boundary survives in some chunk."""
        sentences = [f"Unique sentence {i} is here." for i in range(400)]
        chunks = chunk_pages(pages((1, " ".join(sentences))))
        joined = " ".join(c.text for c in chunks)
        for i in (0, 50, 120, 200, 300, 399):
            assert f"Unique sentence {i} is here." in joined

    def test_heading_is_captured(self):
        chunks = chunk_pages(
            pages(
                (
                    1,
                    "3.2 TERMINATION\n"
                    + "This section sets out the rules that apply when the "
                    * 20
                    + "agreement comes to an end.",
                )
            )
        )
        assert chunks
        assert chunks[0].heading_path
        assert "TERMINATION" in chunks[0].heading_path[0]

    def test_empty_pages_are_skipped(self):
        chunks = chunk_pages(pages((1, ""), (2, "   "), (3, "x" * 300)))
        assert len(chunks) == 1
        assert chunks[0].page_start == 3
