"""Metadata extraction — document type, title, expiry date.

These are the deterministic rules the expiry question relies on. If these
regress, the "which leases expire next year" answer silently degrades into
prose, so they are pinned by tests rather than by inspection.
"""

from datetime import date

import pytest

from app.modules.ingestion.metadata import (
    classify_doc_type,
    extract_metadata,
    extract_parties,
    extract_title,
    find_expiry_date,
)


class TestExpiryDate:
    def test_finds_expiry_date(self):
        text = "LEASE AGREEMENT\nTerm: 36 months.\nExpiry Date: 30 June 2027"
        expiry, evidence = find_expiry_date(text)
        assert expiry == date(2027, 6, 30)
        assert evidence and "30 June 2027" in evidence

    def test_ignores_effective_date(self):
        """An effective date on a previous line must not suppress a real expiry."""
        text = (
            "SERVICE AGREEMENT\n"
            "Effective Date: 1 January 2025\n"
            "This Agreement shall terminate on 14 February 2028.\n"
        )
        expiry, _ = find_expiry_date(text)
        assert expiry == date(2028, 2, 14)

    def test_ignores_effective_date_on_same_line(self):
        text = "Agreement dated 1 January 2025 and Expiry Date: 30 June 2027"
        expiry, _ = find_expiry_date(text)
        assert expiry == date(2027, 6, 30)

    def test_rejects_generic_until(self):
        """'until' matches deadlines, not expiry — it must not be a keyword."""
        text = "Payment is due until 15 March 2026."
        expiry, _ = find_expiry_date(text)
        assert expiry is None

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("31 March 2027", date(2027, 3, 31)),
            ("March 31, 2027", date(2027, 3, 31)),
            ("2027-03-31", date(2027, 3, 31)),
            ("03/31/2027", date(2027, 3, 31)),
        ],
    )
    def test_date_formats(self, raw, expected):
        text = f"Expiry Date: {raw}"
        expiry, _ = find_expiry_date(text)
        assert expiry == expected

    def test_no_expiry_returns_none(self):
        expiry, evidence = find_expiry_date("An open-ended policy with no end date.")
        assert expiry is None
        assert evidence is None


class TestDocType:
    def test_title_beats_body_vocabulary(self):
        """A lease that mentions 'invoice' in its body is still a lease."""
        text = (
            "COMMERCIAL LEASE AGREEMENT\n"
            "The tenant shall pay rent by invoice monthly.\n"
            "Invoices are due within 30 days.\n"
        )
        doc_type, confidence = classify_doc_type(text)
        assert doc_type == "lease"
        assert confidence >= 0.85

    def test_nda(self):
        text = "MUTUAL NON-DISCLOSURE AGREEMENT\nParties agree to confidentiality."
        assert classify_doc_type(text)[0] == "nda"

    def test_policy(self):
        text = "INFORMATION SECURITY POLICY\nAll staff must comply."
        assert classify_doc_type(text)[0] == "policy"

    def test_mou_counts_as_contract(self):
        text = "MEMORANDUM OF UNDERSTANDING\nThis MOU sets out terms."
        assert classify_doc_type(text)[0] == "contract"

    def test_invoice(self):
        text = "INVOICE\nBill To: Northgate Holdings\nPayment Due: 30 days."
        assert classify_doc_type(text)[0] == "invoice"

    def test_unknown_document_is_other(self):
        text = "Some entirely unrelated notes about catering preferences."
        assert classify_doc_type(text)[0] == "other"


class TestTitleAndParties:
    def test_title_from_heading(self):
        text = "HARBOUR STREET LEASE AGREEMENT\n\nBetween Harbour Estates Ltd and ..."
        assert extract_title(text, "harbour-street-lease.pdf") == (
            "Harbour Street Lease Agreement"
        )

    def test_title_falls_back_to_filename(self):
        assert (
            extract_title("some body text without a title", "meridian_park_lease.pdf")
            == "meridian park lease"
        )

    def test_parties_extracted(self):
        text = (
            "COMMERCIAL LEASE AGREEMENT\n"
            "between Harbour Estates Limited and Northgate Holdings PLC\n"
        )
        parties = extract_parties(text)
        assert len(parties) == 2
        assert "Harbour" in parties[0]
        assert "Northgate" in parties[1]


class TestExtractMetadata:
    def test_combined(self):
        text = (
            "MERIDIAN PARK LEASE AGREEMENT\n"
            "between Meridian Holdings and Aurora Capital\n"
            "Expiry Date: 15 November 2027\n"
        )
        meta = extract_metadata(text, "meridian-park-lease.pdf")
        assert meta.doc_type == "lease"
        assert meta.expiry_date == date(2027, 11, 15)
        assert meta.title
        assert len(meta.parties) == 2

    def test_as_dict_is_json_safe(self):
        meta = extract_metadata("INVOICE\nExpiry Date: 1 January 2026", "x.pdf")
        payload = meta.as_dict()
        assert payload["expiry_date"] == "2026-01-01"
        assert isinstance(payload["parties"], list)
