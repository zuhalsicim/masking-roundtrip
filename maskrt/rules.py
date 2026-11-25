"""Detector (a): rules and regular expressions for structured personal data.

Each rule returns Detection objects with character offsets. The rules know nothing
about the test set's labels; they were written from the formats themselves.
"""

from __future__ import annotations

import re

from .spans import Detection

# --- e-mail -------------------------------------------------------------------

_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-zA-Z]{2,}\b")

# --- IBAN ---------------------------------------------------------------------
# Two letters, two check digits, then 11 to 30 letters or digits, optionally in groups of four.
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")


def iban_checksum_ok(value: str) -> bool:
    """ISO 13616 check: move the first four characters to the end, letters to numbers, mod 97 == 1."""
    s = value.replace(" ", "").upper()
    if len(s) < 15:
        return False
    digits = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(digits) % 97 == 1


# --- phone ----------------------------------------------------------------------
# International (+49 ..., +44 ...), national with a leading 0, and the US form (614) 555-0142.
_PHONE = re.compile(
    r"(?<![\w+])(?:"
    r"\+\d{1,3}(?:[ \-]?\(0\))?(?:[ \-/]?\d{1,5}){2,6}"
    r"|\(0\d{2,5}\)[ \-/]?\d{1,4}(?:[ \-]?\d{1,4}){0,4}"
    r"|0\d{2,5}(?:[ \-/]?\d{1,5}){1,5}"
    r"|\(\d{3}\) ?\d{3}-\d{4}"
    r")(?![\w])"
)


def _digit_count(s: str) -> int:
    return sum(c.isdigit() for c in s)


# --- dates of birth -------------------------------------------------------------
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Januar|Februar|März|Mai|Juni|Juli|Oktober|Dezember|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Okt|Nov|Dec|Dez"
)
_DATE = re.compile(
    r"\b(?:"
    r"\d{1,2}\.\s?\d{1,2}\.\s?\d{4}"  # 17.06.1989
    r"|\d{4}-\d{2}-\d{2}"  # 1999-04-12
    r"|\d{1,2}/\d{1,2}/\d{4}"  # 03/05/1992
    rf"|\d{{1,2}}\.?\s(?:{_MONTHS})\.?\s\d{{4}}"  # 14 August 1987, 3. Mai 1990
    rf"|(?:{_MONTHS})\.?\s\d{{1,2}},?\s\d{{4}}"  # May 3, 2015
    r")\b"
)
# A date counts as a date of birth only when a birth word stands shortly before it.
_BIRTH_CONTEXT = re.compile(
    r"(?:\bgeb\.|\bgeboren|\bGeburtsdatum|\bGeburtstag|\bgeb\.-Datum|\*|\bborn\b|\bdate of birth|\bDOB\b|"
    r"\bD\.O\.B\.|\bbirthday|\bbirth date)",
    re.IGNORECASE,
)
_BIRTH_WINDOW = 30

# --- customer, employee, member and contract numbers -----------------------------
_ID_KEYWORDS = (
    r"Kundennummer|Kunden-Nr\.?|Kd\.-Nr\.?|Personalnummer|Personal-Nr\.?|Mitgliedsnummer|Mitglieds-Nr\.?|"
    r"Vertragsnummer|Vertrags-Nr\.?|Versicherungsnummer|"
    r"customer number|customer no\.?|customer|employee number|employee no\.?|staff number|staff no\.?|"
    r"account ID|account number|account reference|policy number|policy no\.?|"
    r"membership number|membership, number|member number|member no\.?"
)
_ID = re.compile(
    rf"(?:{_ID_KEYWORDS})(?:\s*(?:is|:|,|=)\s*|\s+)(?P<value>(?:[A-Z]{{1,4}}[- ]?)?\d[\d-]*\d)\b",
    re.IGNORECASE,
)

# --- postal addresses -------------------------------------------------------------
_DE_SUFFIX = (
    r"straße|strasse|str\.|weg|allee|platz|gasse|ring|damm|ufer|steig|pfad|chaussee|markt|hof|berg|"
    r"garten|hain|feld|winkel|stieg|kamp|twiete"
)
_DE_STREET = (
    rf"(?:[A-ZÄÖÜ][a-zäöüß-]*(?:{_DE_SUFFIX})"
    r"|(?:Am|An der|An den|Im|In der|Auf dem|Auf der|Zum|Zur|Hinter dem|Unter den) [A-ZÄÖÜ][a-zäöüß-]+)"
    r" \d{1,4}\s?[a-z]?\b"
)
_DE_CITY = r"(?:,\s*|\s+)\d{5} [A-ZÄÖÜ][\wäöüß-]+(?: (?:am|an der|im) [A-ZÄÖÜ][\wäöüß-]+)?"
_EN_TYPES = (
    r"Road|Rd|Street|St|Lane|Ln|Drive|Dr|Avenue|Ave|Close|Way|Mews|Court|Ct|Place|Pl|Crescent|Terrace|"
    r"Grove|Gardens|Square|Row|Hill|Boulevard|Blvd"
)
_EN_STREET = (
    r"(?:(?:Flat|Apartment|Apt\.?|Unit) \d{1,4}[A-Za-z]?,\s*)?"
    rf"\d{{1,5}}[A-Za-z]? (?:[A-Z][a-z]+ ){{1,3}}(?:{_EN_TYPES})\b\.?"
)
_UK_POSTCODE = r"[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}"
_EN_CITY = rf",\s*[A-Z][a-z]+(?: [A-Z][a-z]+)?(?:,? (?:{_UK_POSTCODE})|, [A-Z]{{2}} \d{{5}}(?:-\d{{4}})?)?"
_ADDRESS = re.compile(rf"\b(?:{_DE_STREET}(?:{_DE_CITY})?|{_EN_STREET}(?:{_EN_CITY})?)")


def detect_rules(text: str, require_iban_checksum: bool = False) -> list[Detection]:
    """Run every rule. Overlaps are left in; the masking step resolves them."""
    found: list[Detection] = []
    for m in _EMAIL.finditer(text):
        found.append(Detection(m.start(), m.end(), "EMAIL", "rules"))
    for m in _IBAN.finditer(text):
        if not require_iban_checksum or iban_checksum_ok(m.group()):
            found.append(Detection(m.start(), m.end(), "IBAN", "rules"))
    for m in _PHONE.finditer(text):
        value = m.group().rstrip(" -/")
        if 7 <= _digit_count(value) <= 15:
            found.append(Detection(m.start(), m.start() + len(value), "PHONE", "rules"))
    for m in _DATE.finditer(text):
        window = text[max(0, m.start() - _BIRTH_WINDOW) : m.start()]
        if _BIRTH_CONTEXT.search(window):
            found.append(Detection(m.start(), m.end(), "DATE_OF_BIRTH", "rules"))
    for m in _ID.finditer(text):
        found.append(Detection(m.start("value"), m.end("value"), "CUSTOMER_ID", "rules"))
    for m in _ADDRESS.finditer(text):
        found.append(Detection(m.start(), m.end(), "ADDRESS", "rules"))
    return _drop_contained(found)


def _drop_contained(found: list[Detection]) -> list[Detection]:
    """A phone match inside an IBAN or an ID inside an address says nothing new: keep the outer one."""
    keep = []
    for d in found:
        inside = any(
            o is not d and o.start <= d.start and d.end <= o.end and (o.end - o.start) > (d.end - d.start)
            for o in found
        )
        if not inside:
            keep.append(d)
    return sorted(keep, key=lambda d: (d.start, -d.end))
