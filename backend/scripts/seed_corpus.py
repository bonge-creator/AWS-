"""Generate the synthetic document corpus as real PDFs.

The corpus is deliberately small but realistic: leases with expiry dates spread
across years, contracts, policies, an NDA, a report and an invoice. Every
document is generated with real extractable text so the pipeline, the metadata
extractor and the citations all work on genuine documents rather than fixtures.
"""

from pathlib import Path

from fpdf import FPDF

CORPUS_DIR = Path(__file__).resolve().parent.parent / "seed" / "corpus"


def _latin1(text: str) -> str:
    """Core PDF fonts are latin-1 only; map the typographic characters we use."""
    return (
        text.replace("—", "-")
        .replace("–", "-")
        .replace("‘", "'")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("…", "...")
    )


class Doc(FPDF):
    def __init__(self, title: str, subject: str = ""):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=18)
        self.doc_title = title
        self.doc_subject = subject
        self.set_title(title)
        self.set_author("Northbridge Asset Management")
        self.set_creator("Ask the Archive seed corpus")

    def header(self):
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(110, 110, 110)
        self.cell(0, 6, f"{self.doc_title}", align="R")
        self.ln(8)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")

    def title_block(self, title: str, subtitle: str):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(20, 20, 20)
        self.multi_cell(0, 9, _latin1(title))
        self.ln(2)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(90, 90, 90)
        self.multi_cell(0, 6, _latin1(subtitle))
        self.ln(6)

    def heading(self, text: str):
        self.set_x(self.l_margin)
        self.ln(3)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(20, 20, 20)
        self.multi_cell(0, 7, _latin1(text))
        self.ln(1)

    def body(self, text: str):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(35, 35, 35)
        self.multi_cell(0, 5.5, _latin1(text))
        self.ln(1)

    def field(self, label: str, value: str):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 10)
        self.cell(46, 6, _latin1(label))
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 6, _latin1(value))


def _write(doc: Doc, filename: str) -> Path:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    path = CORPUS_DIR / filename
    doc.output(str(path))
    return path


def harbour_street_lease() -> Path:
    d = Doc("Harbour Street Lease")
    d.add_page()
    d.title_block(
        "COMMERCIAL LEASE AGREEMENT",
        "Harbour Street Property, Unit 4 — Northbridge Asset Management and Calverton Trading Ltd",
    )
    d.field("Reference:", "NB/LSE/2024/0117")
    d.field("Property:", "Harbour Street Property, Unit 4, Northbridge")
    d.field("Effective Date:", "1 July 2024")
    d.field("Expiry Date:", "30 June 2027")
    d.field("Term:", "Three (3) years from the Effective Date")
    d.ln(4)
    d.heading("1. PARTIES")
    d.body(
        "This Lease is made between Northbridge Asset Management (the Landlord) and "
        "Calverton Trading Ltd (the Tenant). The Landlord lets the Premises to the "
        "Tenant on the terms set out below."
    )
    d.heading("2. RENT")
    d.body(
        "The annual rent is forty-eight thousand pounds (£48,000) exclusive of rates, "
        "service charge and VAT, payable quarterly in advance on the first business day "
        "of each quarter by standing order to the Landlord's nominated account. The rent "
        "is reviewed on each fifth anniversary of the Effective Date by reference to the "
        "Retail Prices Index."
    )
    d.heading("3. DEPOSIT")
    d.body(
        "On the commencement of the Term the Tenant shall pay a rent deposit equal to one "
        "quarter of the annual rent, being twelve thousand pounds (£12,000), to be held "
        "by the Landlord without interest and applied against the final months of the Term."
    )
    d.heading("4. TERM AND TERMINATION")
    d.body(
        "The Term of this Lease shall expire on 30 June 2027 unless terminated earlier "
        "in accordance with this Clause. The Tenant may break the Lease at the end of the "
        "second year by giving not less than six months' written notice. Any earlier "
        "termination by the Tenant requires the Landlord's consent, not to be unreasonably withheld."
    )
    d.heading("5. USE OF PREMISES")
    d.body(
        "The Tenant shall use the Premises solely as an office and light storage facility "
        "and for no other purpose without the Landlord's prior written consent. The Tenant "
        "shall not carry out any activity that causes a nuisance to the occupiers of the "
        "surrounding buildings."
    )
    d.heading("6. REPAIRS AND INSURANCE")
    d.body(
        "The Tenant shall keep the interior of the Premises in good repair, clean and "
        "decorative, and shall insure the plate glass, internal fittings and contents "
        "with a reputable insurer. The Landlord shall maintain the structure, roof and "
        "external fabric of the Building."
    )
    d.add_page()
    d.heading("7. SERVICE CHARGE")
    d.body(
        "The Tenant shall pay a service charge equal to a proportionate share of the "
        "Landlord's reasonable costs of operating and maintaining the Building. The "
        "Landlord shall provide a statement of account within four months of the end of "
        "each financial year."
    )
    d.heading("8. NOTICES")
    d.body(
        "Notices under this Lease must be in writing and delivered by hand or by recorded "
        "delivery to the registered office of the relevant party. Notices are deemed "
        "received on the date of delivery."
    )
    d.heading("9. ENTIRE AGREEMENT")
    d.body(
        "This Lease constitutes the entire agreement between the parties and supersedes "
        "all previous discussions. No variation of this Lease is effective unless in "
        "writing and signed by both parties."
    )
    return _write(d, "harbour-street-lease.pdf")


def meridian_lease() -> Path:
    d = Doc("Meridian Park Lease")
    d.add_page()
    d.title_block(
        "COMMERCIAL LEASE AGREEMENT",
        "Meridian Park, Building 2 — Northbridge Asset Management and Halden Industrial Group",
    )
    d.field("Reference:", "NB/LSE/2025/0044")
    d.field("Property:", "Meridian Park, Building 2, Unit 12, Northbridge")
    d.field("Effective Date:", "1 December 2025")
    d.field("Expiry Date:", "15 November 2027")
    d.field("Term:", "Twenty-two (22) months from the Effective Date")
    d.ln(4)
    d.heading("1. PARTIES")
    d.body(
        "This Lease is made between Northbridge Asset Management (the Landlord) and "
        "Halden Industrial Group (the Tenant)."
    )
    d.heading("2. RENT")
    d.body(
        "The annual rent is seventy-two thousand five hundred pounds (£72,500) exclusive "
        "of VAT, payable monthly in advance by direct debit. The Tenant shall pay all "
        "rates, utilities and service charges relating to the Premises."
    )
    d.heading("3. TERM AND TERMINATION")
    d.body(
        "This Lease shall expire on 15 November 2027. The Tenant may terminate the Lease "
        "at any time by giving six months' written notice, provided that no arrears of "
        "rent are outstanding at the date of the notice."
    )
    d.heading("4. SECURITY")
    d.body(
        "The Tenant shall provide an on-demand bank guarantee equal to three months' rent "
        "within ten business days of the Effective Date and shall maintain that guarantee "
        "throughout the Term."
    )
    d.heading("5. USE")
    d.body(
        "The Premises shall be used as a production and assembly facility and ancillary "
        "office use. The Tenant shall not store hazardous materials on the Premises "
        "without the Landlord's written consent."
    )
    d.heading("6. ASSIGNMENT")
    d.body(
        "The Tenant shall not assign, sublet or otherwise part with possession of the "
        "Premises without the Landlord's prior written consent, such consent not to be "
        "unreasonably withheld or delayed."
    )
    d.add_page()
    d.heading("7. CONDITION AND REPAIRS")
    d.body(
        "The Tenant shall keep the Premises in good and working repair, fair wear and tear "
        "excepted, and shall comply with all applicable health, safety and environmental "
        "legislation in relation to its occupation of the Premises."
    )
    d.heading("8. INSURANCE")
    d.body(
        "The Tenant shall insure its plant, machinery, stock and contents and shall "
        "produce evidence of that insurance to the Landlord on reasonable request."
    )
    d.heading("9. ENTRY")
    d.body(
        "The Landlord may enter the Premises on reasonable notice to inspect the "
        "condition of the Building, provided that the Tenant's operations are not "
        "materially disrupted."
    )
    return _write(d, "meridian-park-lease.pdf")


def northgate_lease() -> Path:
    d = Doc("Northgate Warehouse Lease")
    d.add_page()
    d.title_block(
        "WAREHOUSE LEASE AGREEMENT",
        "Northgate Warehouse, Northbridge — Northbridge Asset Management and Selby Distribution Ltd",
    )
    d.field("Reference:", "NB/LSE/2023/0209")
    d.field("Property:", "Northgate Warehouse, Unit 6, Northbridge")
    d.field("Effective Date:", "1 May 2023")
    d.field("Expiry Date:", "30 April 2026")
    d.ln(4)
    d.heading("1. PARTIES")
    d.body(
        "This Lease is made between Northbridge Asset Management (the Landlord) and "
        "Selby Distribution Ltd (the Tenant)."
    )
    d.heading("2. RENT")
    d.body(
        "The annual rent is thirty-one thousand two hundred pounds (£31,200) payable "
        "quarterly in advance."
    )
    d.heading("3. TERM")
    d.body(
        "The Term of this Lease shall expire on 30 April 2026. The Lease was subject to "
        "an agreed renewal option exercisable by the Tenant on or before 31 October 2025."
    )
    d.heading("4. USE")
    d.body(
        "The Premises shall be used for the storage and onward distribution of consumer "
        "goods and for no other purpose."
    )
    d.heading("5. CONDITION")
    d.body(
        "The Tenant shall keep the Premises clean, secure and in good repair, fair wear "
        "and tear excepted, and shall not make structural alterations without consent."
    )
    return _write(d, "northgate-warehouse-lease.pdf")


def kestrel_contract() -> Path:
    d = Doc("Kestrel Facilities Contract")
    d.add_page()
    d.title_block(
        "FACILITIES MANAGEMENT SERVICES AGREEMENT",
        "Northbridge Asset Management and Kestrel Facilities Services Ltd",
    )
    d.field("Reference:", "NB/SVC/2025/0031")
    d.field("Effective Date:", "1 April 2025")
    d.field("Contract Value:", "£250,000 over three years")
    d.field("Termination Date:", "31 March 2028")
    d.ln(4)
    d.heading("1. PARTIES")
    d.body(
        "This Agreement is made between Northbridge Asset Management (the Landlord) "
        "and Kestrel Facilities Services Ltd (the Supplier). The Landlord appoints the "
        "Supplier to provide the Services to the Building on the terms set out below."
    )
    d.heading("2. SCOPE OF SERVICES")
    d.body(
        "The Supplier shall provide planned preventative maintenance, statutory "
        "inspection, reactive repair and energy management services to the Building. "
        "The Supplier shall maintain a twenty-four hour emergency call-out service with a "
        "response time of four hours for critical plant failures."
    )
    d.heading("3. CHARGES")
    d.body(
        "The annual charge for the services is eighty-three thousand pounds (£83,000) "
        "plus an agreed schedule of rates for work outside the planned maintenance "
        "programme. Charges are invoiced quarterly in arrears and payable within thirty "
        "days of receipt of a valid invoice."
    )
    d.heading("4. PERFORMANCE")
    d.body(
        "The Supplier shall achieve a service availability of not less than 98 per cent "
        "measured monthly across the Building's critical plant. The Supplier shall "
        "provide a monthly performance report within ten working days of each month end."
    )
    d.heading("5. INDEMNITY AND INSURANCE")
    d.body(
        "The Supplier shall indemnify the Landlord against all loss arising from the "
        "Supplier's negligence or breach of this Agreement, and shall maintain public "
        "liability insurance of not less than five million pounds (£5,000,000) per "
        "occurrence and employer liability insurance of not less than ten million pounds (£10,000,000)."
    )
    d.heading("6. TERM AND TERMINATION")
    d.body(
        "This Agreement shall expire on 31 March 2028 unless terminated earlier. Either "
        "party may terminate for material breach not remedied within thirty days of "
        "written notice. The Supplier may not assign this Agreement without consent."
    )
    d.add_page()
    d.heading("7. HEALTH AND SAFETY")
    d.body(
        "The Supplier shall comply with all applicable health and safety legislation and "
        "shall ensure that all its operatives hold the required certifications for the "
        "plant they service."
    )
    d.heading("8. DATA AND RECORDS")
    d.body(
        "The Supplier shall maintain complete maintenance records for each item of "
        "plant serviced and shall provide those records to the Landlord on request."
    )
    d.heading("9. GOVERNANCE")
    d.body(
        "The parties shall hold a quarterly service review meeting to discuss "
        "performance, outstanding defects and the forward maintenance programme."
    )
    return _write(d, "kestrel-facilities-contract.pdf")


def ridgeline_contract() -> Path:
    d = Doc("Ridgeline Supply Agreement")
    d.add_page()
    d.title_block(
        "SUPPLY AND SERVICES AGREEMENT",
        "Northbridge Asset Management and Ridgeline Supply Co Ltd",
    )
    d.field("Reference:", "NB/PUR/2026/0018")
    d.field("Effective Date:", "15 February 2026")
    d.field("Contract Value:", "£186,000 over two years")
    d.field("Termination Date:", "14 February 2028")
    d.ln(4)
    d.heading("1. PARTIES")
    d.body(
        "This Agreement is made between Northbridge Asset Management (the Buyer) and "
        "Ridgeline Supply Co Ltd (the Supplier). The Supplier shall supply the Goods and "
        "Services described in Schedule A on the terms set out below."
    )
    d.heading("2. SUPPLY")
    d.body(
        "The Supplier shall supply and deliver stationery, protective equipment and "
        "general consumables to the sites listed in Schedule A, in the quantities and at "
        "the unit rates set out in that Schedule."
    )
    d.heading("3. PRICES AND CHARGING")
    d.body(
        "Prices are fixed for the first twelve months of the Term and may be increased "
        "once in each Contract Year thereafter by no more than the Retail Prices Index. "
        "The Supplier shall not charge for delivery to the sites listed in Schedule A."
    )
    d.heading("4. DELIVERY")
    d.body(
        "Deliveries shall be made between 07:00 and 15:00 on business days. The Supplier "
        "shall give not less than two business days' notice of any planned service "
        "interruption. Emergency deliveries require one hour's notice."
    )
    d.heading("5. PAYMENT")
    d.body(
        "The Buyer shall pay each correctly rendered invoice within forty-five days of "
        "the end of the month in which the goods were supplied. The Supplier shall "
        "submit invoices monthly in arrears."
    )
    d.heading("6. QUALITY")
    d.body(
        "All goods shall conform to the applicable British Standards and shall be fit for "
        "the purpose notified to the Supplier at the time of ordering. The Supplier "
        "warrants that the goods are free from defects in materials and workmanship."
    )
    d.heading("7. ENVIRONMENTAL REQUIREMENTS")
    d.body(
        "The Supplier shall supply recycled content stationery where an equivalent "
        "recycled product is available and shall publish its annual sustainability "
        "statement each year."
    )
    d.heading("8. TERM AND TERMINATION")
    d.body(
        "This Agreement shall expire on 14 February 2028. The Buyer may terminate "
        "immediately if the Supplier commits a material breach that is not capable of "
        "remedy or if the Supplier becomes insolvent."
    )
    return _write(d, "ridgeline-supply-agreement.pdf")


def data_policy() -> Path:
    d = Doc("Data Retention Policy")
    d.add_page()
    d.title_block(
        "DATA RETENTION AND HANDLING POLICY",
        "Northbridge Asset Management — Information Governance",
    )
    d.field("Policy Reference:", "NB/POL/IG/04")
    d.field("Effective Date:", "1 April 2025")
    d.field("Review Date:", "1 April 2027")
    d.field("Approved by:", "Information Governance Board")
    d.ln(4)
    d.heading("1. PURPOSE")
    d.body(
        "This policy sets out how long Northbridge Asset Management retains operational "
        "records, who may access them and how they must be disposed of. It applies to "
        "all employees, contractors and systems processing company records."
    )
    d.heading("2. SCOPE")
    d.body(
        "This policy covers paper and electronic records held in company systems, "
        "including finance, property, HR and procurement records."
    )
    d.heading("3. RETENTION SCHEDULE")
    d.body(
        "Financial and accounting records shall be retained for six years from the end "
        "of the financial year to which they relate. Property leases, licences and "
        "associated correspondence shall be retained for six years after the lease or "
        "licence ends. Human resources records shall be retained for six years after "
        "the employment relationship ends."
    )
    d.heading("4. DISPOSAL")
    d.body(
        "Records that have reached the end of their retention period shall be securely "
        "destroyed by cross-cut shredding or by an approved digital destruction service. "
        "A disposal record shall be retained by the Information Governance team."
    )
    d.heading("5. ACCESS CONTROL")
    d.body(
        "Access to records is granted on the basis of business need and is reviewed "
        "annually. Where possible, records shall be pseudonymised before analysis. "
        "Unauthorised access to or disclosure of records is a disciplinary matter."
    )
    d.heading("6. INCIDENT RESPONSE")
    d.body(
        "Any suspected loss or unauthorised disclosure of a record shall be reported to "
        "the Information Governance team within twenty-four hours of discovery."
    )
    d.heading("7. BREACHES")
    d.body(
        "The Landlord's Data Protection Officer shall report any personal data breach to "
        "the supervisory authority within seventy-two hours where the breach is likely "
        "to result in a risk to the rights and freedoms of individuals."
    )
    return _write(d, "data-retention-policy.pdf")


def security_policy() -> Path:
    d = Doc("Information Security Policy")
    d.add_page()
    d.title_block(
        "INFORMATION SECURITY POLICY",
        "Northbridge Asset Management — Information Governance",
    )
    d.field("Policy Reference:", "NB/POL/IS/01")
    d.field("Effective Date:", "1 October 2025")
    d.field("Review Date:", "1 October 2027")
    d.ln(4)
    d.heading("1. OBJECTIVE")
    d.body(
        "This policy defines the minimum security controls that protect the "
        "confidentiality, integrity and availability of company information systems and "
        "the information they hold."
    )
    d.heading("2. ACCESS CONTROL")
    d.body(
        "Access is granted on the principles of least privilege and need to know, and is "
        "granted for a defined period. Multi-factor authentication is required for all "
        "remote access and for all administrative accounts. Access is revoked on the "
        "day a person's role changes or their employment ends."
    )
    d.heading("3. AUTHENTICATION AND PASSWORDS")
    d.body(
        "Passwords must be at least fourteen characters long, must not be reused across "
        "systems, and must be stored in an approved password manager. Credentials must "
        "never be shared, and must never be written into documentation or source code."
    )
    d.heading("4. ENCRYPTION")
    d.body(
        "Company data shall be encrypted at rest using AES-256 with a centrally managed "
        "key, and in transit using TLS 1.2 or higher. Document originals stored outside "
        "the corporate network shall remain encrypted."
    )
    d.heading("5. AUDIT AND MONITORING")
    d.body(
        "Access to sensitive systems and documents is logged and the logs are reviewed "
        "monthly by the Information Governance team. Retrieval of documents from the "
        "archive service is recorded against the requesting user."
    )
    d.heading("6. INCIDENT MANAGEMENT")
    d.body(
        "Security incidents shall be reported to the Security Operations Centre within "
        "one hour of discovery and shall be triaged within four hours."
    )
    d.heading("7. OFFBOARDING")
    d.body(
        "On the last day of employment all accounts shall be disabled, all equipment "
        "recovered, and all copies of company information on personal devices shall be "
        "removed and confirmed in writing."
    )
    return _write(d, "information-security-policy.pdf")


def nda() -> Path:
    d = Doc("Aurora Mutual NDA")
    d.add_page()
    d.title_block(
        "MUTUAL NON-DISCLOSURE AGREEMENT",
        "Northbridge Asset Management and Aurora Biotech Ltd",
    )
    d.field("Reference:", "NB/NDA/2026/0007")
    d.field("Effective Date:", "9 March 2026")
    d.field("Expiry Date:", "8 March 2029")
    d.ln(4)
    d.heading("1. PARTIES")
    d.body(
        "This Agreement is made between Northbridge Asset Management (the Discloser) and "
        "Aurora Biotech Ltd (the Recipient). Each party may disclose confidential "
        "information to the other and each party may receive such information."
    )
    d.heading("2. CONFIDENTIAL INFORMATION")
    d.body(
        "Confidential Information means all non-public information disclosed by one "
        "party to the other, whether disclosed orally, in writing or by inspection of "
        "premises, that is identified as confidential or that ought reasonably to be "
        "treated as confidential."
    )
    d.heading("3. OBLIGATIONS")
    d.body(
        "The Recipient shall keep the Discloser's Confidential Information secret, shall "
        "not disclose it to any third party, and shall use it only for the purpose of "
        "evaluating a proposed collaboration between the parties."
    )
    d.heading("4. EXCLUSIONS")
    d.body(
        "The obligations do not apply to information that is or becomes public through "
        "no breach of this Agreement, that the Recipient already lawfully held before "
        "disclosure, or that the Recipient develops independently of the Discloser's "
        "Confidential Information."
    )
    d.heading("5. TERM")
    d.body(
        "This Agreement shall expire on 8 March 2029. The obligations of confidentiality "
        "survive expiry for a period of five years in respect of commercial information "
        "and indefinitely in respect of trade secrets."
    )
    d.heading("6. GOVERNING LAW")
    d.body(
        "This Agreement is governed by the laws of England and Wales and the parties "
        "submit to the exclusive jurisdiction of the courts of England and Wales."
    )
    return _write(d, "aurora-mutual-nda.pdf")


def survey_report() -> Path:
    d = Doc("Infrastructure Survey 2026")
    d.add_page()
    d.title_block(
        "ANNUAL INFRASTRUCTURE CONDITION SURVEY",
        "Northbridge Asset Management — Property and Technical Services",
    )
    d.field("Report Reference:", "NB/RPT/2026/002")
    d.field("Survey Date:", "18 February 2026")
    d.field("Surveyor:", "Pentland Building Surveyors")
    d.field("Effective Date:", "1 March 2026")
    d.ln(4)
    d.heading("1. PURPOSE AND SCOPE")
    d.body(
        "This report records the condition of the building fabric and mechanical "
        "services at the properties inspected: Harbour Street Property, Meridian Park "
        "Building 2, and Northgate Warehouse. The survey was a visual inspection with "
        "no opening up of the structure and no testing of services."
    )
    d.heading("2. SUMMARY OF FINDINGS")
    d.body(
        "Overall the portfolio is in a fair and stable condition. The most significant "
        "issue identified is corrosion of the rainwater goods at Northgate Warehouse, "
        "which is estimated at four thousand two hundred pounds (£4,200) to remedy. "
        "Harbour Street is in good condition with no defects requiring action within "
        "twelve months."
    )
    d.heading("3. HARBOUR STREET PROPERTY")
    d.body(
        "Roof coverings are sound with an estimated remaining life of eight years. "
        "The lift installation is compliant and its certification is valid for "
        "fourteen months. Internal fittings are generally serviceable."
    )
    d.heading("4. MERIDIAN PARK BUILDING 2")
    d.body(
        "The external envelope is in good condition. The loading bay shutter requires "
        "replacement within three years at an estimated cost of six thousand pounds (£6,000). "
        "The electrical distribution board does not meet the current recommended "
        "configuration for future-proofing and should be upgraded within five years."
    )
    d.heading("5. NORTHGATE WAREHOUSE")
    d.body(
        "Rainwater goods show significant corrosion and require replacement. Floor "
        "loading is adequate for the current use. The loading bay doors are serviceable."
    )
    d.heading("6. RECOMMENDED PRIORITIES")
    d.body(
        "Immediate: replace rainwater goods at Northgate Warehouse. Twelve months: "
        "upgrade electrical distribution boards at Meridian Park. Three years: replace "
        "loading bay shutter at Meridian Park."
    )
    return _write(d, "infrastructure-survey-2026.pdf")


def mou() -> Path:
    d = Doc("Transit Authority MOU")
    d.add_page()
    d.title_block(
        "MEMORANDUM OF UNDERSTANDING",
        "Northbridge Asset Management and the Northbridge Transit Authority",
    )
    d.field("Reference:", "NB/MOU/2026/0011")
    d.field("Effective Date:", "20 May 2026")
    d.field("Expiry Date:", "19 May 2028")
    d.ln(4)
    d.heading("1. PURPOSE")
    d.body(
        "This Memorandum of Understanding records the parties' shared intention to "
        "collaborate on transport and access arrangements for the Northbridge regeneration "
        "area. It is not intended to create legal obligations and is not legally binding."
    )
    d.heading("2. SCOPE OF COOPERATION")
    d.body(
        "The parties intend to explore joint working on bus routing, cycleway provision "
        "and servicing access to the Harbour Street and Meridian Park sites."
    )
    d.heading("3. WORKING ARRANGEMENTS")
    d.body(
        "The parties will nominate a representative of each organisation within one "
        "month of the Effective Date and will meet quarterly to review progress."
    )
    d.heading("4. TERM")
    d.body(
        "This Memorandum shall expire on 19 May 2028 unless the parties agree in "
        "writing to extend it. Any extension shall be recorded in a signed addendum."
    )
    d.heading("5. NO BINDING OBLIGATION")
    d.body(
        "Nothing in this Memorandum creates any obligation to proceed with any "
        "collaboration, and neither party shall be liable for failure to do so."
    )
    return _write(d, "transit-authority-mou.pdf")


def invoice() -> Path:
    d = Doc("Q4 Facilities Invoice")
    d.add_page()
    d.title_block(
        "INVOICE",
        "Kestrel Facilities Services Ltd — Invoice to Northbridge Asset Management",
    )
    d.field("Invoice Number:", "KFS-2026-0418")
    d.field("Invoice Date:", "28 February 2026")
    d.field("Payment Due:", "30 April 2026")
    d.field("Contract Reference:", "NB/SVC/2025/0031")
    d.ln(4)
    d.heading("CHARGES")
    d.body(
        "Planned preventative maintenance, quarter 4 — £18,250.00. "
        "Reactive repair call-outs — £3,410.00. "
        "Statutory inspection and certification — £2,180.00. "
        "Energy management and reporting — £1,600.00."
    )
    d.heading("TOTAL")
    d.body(
        "Total due excluding VAT: £25,440.00. VAT at twenty per cent: £5,088.00. "
        "Total payable: £30,528.00."
    )
    d.heading("PAYMENT DETAILS")
    d.body(
        "Payment is due by the date shown above and should be referenced with the "
        "invoice number. Please do not send cash. Remittance advice should be sent to "
        "the accounts inbox at the address on the letterhead."
    )
    return _write(d, "kestrel-q4-invoice.pdf")


BUILDERS = [
    ("harbour-street-lease.pdf", harbour_street_lease),
    ("meridian-park-lease.pdf", meridian_lease),
    ("northgate-warehouse-lease.pdf", northgate_lease),
    ("kestrel-facilities-contract.pdf", kestrel_contract),
    ("ridgeline-supply-agreement.pdf", ridgeline_contract),
    ("data-retention-policy.pdf", data_policy),
    ("information-security-policy.pdf", security_policy),
    ("aurora-mutual-nda.pdf", nda),
    ("infrastructure-survey-2026.pdf", survey_report),
    ("transit-authority-mou.pdf", mou),
    ("kestrel-q4-invoice.pdf", invoice),
]


def build_corpus() -> list:
    """Generate every document and return the list of paths."""
    return [builder() for _name, builder in BUILDERS]


if __name__ == "__main__":
    for path in build_corpus():
        print(f"wrote {path.name} ({path.stat().st_size} bytes)")
