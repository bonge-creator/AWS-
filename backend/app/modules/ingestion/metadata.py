"""Metadata extraction — document type, title and expiry date.

Deterministic first: a regex pre-pass finds dates attached to expiry/expiry-
related keywords. The model may refine the result, but it can never invent a
date that the deterministic pass did not find — the LLM output is only accepted
when it agrees with text that actually occurs in the document.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Keywords that mark the date as the document's expiry rather than any other date.
# Deliberately excludes generic words like "until", which match deadlines.
#
# STRONG keywords name the expiry outright. A weak qualifier elsewhere in the
# line ("dated 1 January 2025 and Expiry Date: ...") must not suppress them,
# because the expiry is still the expiry. WEAK keywords ("expires", "expiry")
# are suppressed by a preceding negative context, since "expires" can also
# describe something other than the document itself.
STRONG_EXPIRY_KEYWORDS = [
    "expiry date", "expiration date", "lease end date", "termination date",
    "expires on", "expire on", "shall expire on", "shall terminate on",
    "terminates on", "term ends on", "end date", "renewal date",
    "renews on", "review date",
]

WEAK_EXPIRY_KEYWORDS = [
    "expires", "expiry", "expiration", "valid until", "valid through",
]

EXPIRY_KEYWORDS = STRONG_EXPIRY_KEYWORDS + WEAK_EXPIRY_KEYWORDS

# Dates that must never be mistaken for the expiry date.
NEGATIVE_CONTEXT = [
    "effective date", "dated as of", "date of issue", "issued on", "signed",
    "commencement", "date of agreement", "dated",
]

DOC_TYPE_PATTERNS = [
    ("lease", re.compile(r"\blease\s+agreement\b|\bcommercial\s+lease\b|\btenancy\s+agreement\b|\bwarehouse\s+lease\b|\blease\b", re.I)),
    ("nda", re.compile(r"\bnon[-\s]?disclosure\b|\bconfidentiality\s+agreement\b|\bmutual\s+non[-\s]disclosure\b|\bnda\b", re.I)),
    ("policy", re.compile(r"\bpolicy\b|\bprocedure\s+manual\b|\bguidelines?\b|\bstandard\s+operating\s+procedure\b|\bsop\b", re.I)),
    ("invoice", re.compile(r"\binvoice\b|\bbill\s+to\b|\bpayment\s+due\b|\bremittance\b", re.I)),
    ("report", re.compile(r"\b(?:annual|quarterly|technical|condition|structural|inspection)\s+report\b|\bsurvey\s+report\b|\bcondition\s+survey\b|\bsurvey\b", re.I)),
    ("contract", re.compile(r"\bservice\s+agreement\b|\bmaster\s+services?\s+agreement\b|\bcontract\s+agreement\b|\bstatement\s+of\s+work\b|\bsow\b|\bagreement\b|\bcontract\b", re.I)),
]

# "Memorandum of Understanding" / "MOU" is not in the enum; it maps to contract.
MOU = re.compile(r"\bmemorandum\s+of\s+understanding\b|\bmou\b", re.I)

# The document title is the strongest type signal: bodies mention "lease" and
# "invoice" in passing, but the title states what the document actually is.
TITLE_RULES = [
    ("lease", re.compile(r"\blease\b", re.I)),
    ("nda", re.compile(r"\bnon[-\s]?disclosure\b|\bnda\b", re.I)),
    ("policy", re.compile(r"\bpolicy\b|\bprocedure\b|\bguidelines?\b", re.I)),
    ("invoice", re.compile(r"\binvoice\b|\bbill\b", re.I)),
    ("report", re.compile(r"\breport\b|\bsurvey\b|\bassessment\b", re.I)),
    ("contract", re.compile(r"\bagreement\b|\bcontract\b|\bmemorandum\b|\bmou\b|\bterms\b|\bstatement of work\b", re.I)),
]


@dataclass
class ExtractedMetadata:
    doc_type: Optional[str] = None
    title: Optional[str] = None
    expiry_date: Optional[date] = None
    confidence: float = 0.0
    evidence: Optional[str] = None
    parties: list = None

    def __post_init__(self):
        if self.parties is None:
            self.parties = []

    def as_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "title": self.title,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "confidence": round(self.confidence, 3),
            "expiry_evidence": self.evidence,
            "parties": self.parties,
        }


def _title_line(text: str) -> str:
    """The document's own title: the first meaningful line of the first page."""
    for line in text.split("\n")[:8]:
        candidate = line.strip()
        if len(candidate) >= 6:
            return candidate
    return ""


def classify_doc_type(text: str) -> tuple[str, float]:
    """Return (doc_type, confidence). MOU counts as a contract.

    The title wins when it names a type; otherwise the body is scored by how
    often each type's vocabulary appears, which keeps a lease that happens to
    mention "invoice" from being filed as an invoice.
    """
    if MOU.search(_title_line(text)):
        return "contract", 0.9

    title = _title_line(text)
    for doc_type, pattern in TITLE_RULES:
        if pattern.search(title):
            return doc_type, 0.9

    head = text[:4000]
    best_type, best_score = "other", 0
    for doc_type, pattern in DOC_TYPE_PATTERNS:
        matches = len(pattern.findall(head))
        if matches > best_score:
            best_type, best_score = doc_type, matches
    if best_score == 0:
        return "other", 0.3
    return best_type, min(0.85, 0.5 + 0.07 * best_score)


def _parse_date_near(text: str, position: int) -> Optional[date]:
    """Look for a date within ~120 characters after `position`."""
    window = text[position : position + 160]
    patterns = [
        # 31 March 2027 / March 31, 2027
        re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b"),
        re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"),
        # 2027-03-31
        re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),
        # 03/31/2027
        re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),
    ]
    for pattern in patterns:
        m = pattern.search(window)
        if not m:
            continue
        groups = m.groups()
        try:
            if groups[0].isdigit() and len(groups[0]) == 4:  # ISO
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            elif groups[0].isdigit() and groups[1].isalpha():  # 31 March 2027
                day, month_name, year = int(groups[0]), groups[1].lower(), int(groups[2])
                month = MONTHS.get(month_name)
                if not month:
                    continue
            elif groups[0].isalpha():  # March 31, 2027
                month_name, day, year = groups[0].lower(), int(groups[1]), int(groups[2])
                month = MONTHS.get(month_name)
                if not month:
                    continue
            else:  # 03/31/2027
                month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
            return date(year, month, day)
        except ValueError:
            continue
    return None


def find_expiry_date(text: str) -> tuple[Optional[date], Optional[str]]:
    """Find the expiry/termination date and the sentence that states it."""
    lower = text.lower()
    best: Optional[tuple[date, str]] = None
    best_position = None

    def consider(keyword: str, strong: bool) -> None:
        nonlocal best, best_position
        start = 0
        while True:
            pos = lower.find(keyword, start)
            if pos == -1:
                return
            start = pos + len(keyword)

            if not strong:
                # Reject if a negative-context phrase sits on the same line just
                # before the keyword. Scoped to the line so an unrelated field
                # earlier in the document ("Effective Date: ...\nExpiry Date:
                # ...") cannot suppress a genuine expiry.
                line_start = lower.rfind("\n", 0, pos) + 1
                preceding = lower[max(line_start, pos - 40) : pos]
                if any(neg in preceding for neg in NEGATIVE_CONTEXT):
                    continue

            found = _parse_date_near(text, pos)
            if found is None:
                continue
            if best_position is None or pos < best_position:
                best_position = pos
                snippet_start = max(0, pos - 60)
                snippet = text[snippet_start : pos + 120].replace("\n", " ").strip()
                best = (found, snippet)
            return

    # Strong keywords are searched first: "Expiry Date: ..." is decisive even
    # when an unrelated qualifier appears earlier on the same line.
    for keyword in STRONG_EXPIRY_KEYWORDS:
        consider(keyword, strong=True)
    for keyword in WEAK_EXPIRY_KEYWORDS:
        consider(keyword, strong=False)

    if best is None:
        return None, None
    return best


def extract_title(text: str, filename: str) -> Optional[str]:
    """Prefer an explicit document title line over the filename."""
    for line in text.split("\n")[:12]:
        candidate = line.strip()
        if not candidate or len(candidate) > 160:
            continue
        if candidate.isupper() and len(candidate.split()) >= 2:
            return candidate.title()
        if re.match(r"^[A-Z][\w\s'&,()/\-]{6,120}$", candidate) and not candidate.endswith("."):
            words = candidate.split()
            if 2 <= len(words) <= 14:
                return candidate
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", filename).replace("_", " ").replace("-", " ")
    return stem.strip() or None


def extract_parties(text: str) -> list:
    """Pull 'between X and Y' style party names — used to make answers concrete."""
    m = re.search(
        r"between\s+(?:the\s+)?(.+?)\s+and\s+(.+?)(?:,|\.| dated | \(|\n)",
        text[:4000],
        re.I | re.S,
    )
    if not m:
        return []
    parties = []
    for raw in (m.group(1), m.group(2)):
        cleaned = re.sub(r"\s+", " ", raw).strip(" ,.")
        if 2 < len(cleaned) < 120:
            parties.append(cleaned)
    return parties


def extract_metadata(text: str, filename: str) -> ExtractedMetadata:
    """Deterministic metadata pass."""
    doc_type, confidence = classify_doc_type(text)
    expiry, evidence = find_expiry_date(text)
    return ExtractedMetadata(
        doc_type=doc_type,
        title=extract_title(text, filename),
        expiry_date=expiry,
        confidence=confidence,
        evidence=evidence,
        parties=extract_parties(text),
    )
