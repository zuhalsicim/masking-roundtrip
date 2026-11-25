"""Masking with numbered placeholders, and unmasking of a model's answer.

mask() replaces every detected span with a placeholder such as [PERSON_1]. Within one
document the same value always gets the same placeholder. The mapping from placeholder
to value stays with the caller; it never goes to the model.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .spans import Detection, merge

TITLES = {"herr", "frau", "dr", "dr.", "prof", "prof.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "miss"}


def placeholder(type_: str, n: int) -> str:
    return f"[{type_}_{n}]"


@dataclass
class Replacement:
    start: int  # in the original text
    end: int
    masked_start: int  # in the masked text
    masked_end: int
    placeholder: str
    type: str
    source: str


@dataclass
class MaskResult:
    masked: str
    mapping: dict[str, str]  # placeholder -> value used when unmasking
    replacements: list[Replacement] = field(default_factory=list)


def _norm(value: str, type_: str) -> str:
    v = unicodedata.normalize("NFC", value).casefold()
    if type_ in {"PHONE", "IBAN", "CUSTOMER_ID"}:
        return re.sub(r"[^0-9a-z]", "", v)
    return " ".join(v.split())


def _name_tokens(value: str) -> list[str]:
    tokens = re.findall(r"[\w'-]+\.?", unicodedata.normalize("NFC", value).casefold())
    return [t.rstrip(".") for t in tokens if t not in TITLES]


class _Numbering:
    """Gives out placeholder numbers per type and remembers which value got which."""

    def __init__(self) -> None:
        self.by_key: dict[tuple[str, str], str] = {}
        self.counts: dict[str, int] = {}
        self.people: list[tuple[str, set[str]]] = []  # (placeholder, name tokens seen for it)
        self.values: dict[str, list[str]] = {}

    def get(self, type_: str, value: str) -> str:
        key = (type_, _norm(value, type_))
        ph = self.by_key.get(key)
        if ph is None and type_ == "PERSON":
            ph = self._link_person(value)
        if ph is None:
            self.counts[type_] = self.counts.get(type_, 0) + 1
            ph = placeholder(type_, self.counts[type_])
            if type_ == "PERSON":
                self.people.append((ph, set(_name_tokens(value))))
        elif type_ == "PERSON":
            for i, (p, tokens) in enumerate(self.people):
                if p == ph:
                    self.people[i] = (p, tokens | set(_name_tokens(value)))
        self.by_key[key] = ph
        self.values.setdefault(ph, []).append(value)
        return ph

    def _link_person(self, value: str) -> str | None:
        """"Koch" after "Martin Koch" is the same person, if exactly one earlier name fits.

        Two names fit when the tokens of one are a subset of the tokens of the other.
        With two candidates ("Anna" after "Anna Lehmann" and "Anna Petersen") nothing is linked.
        """
        tokens = set(_name_tokens(value))
        if not tokens:
            return None
        candidates = [p for p, seen in self.people if tokens <= seen or seen <= tokens]
        return candidates[0] if len(candidates) == 1 else None


def mask(text: str, detections: list[Detection]) -> MaskResult:
    spans = merge(detections)
    numbering = _Numbering()
    parts: list[str] = []
    replacements: list[Replacement] = []
    pos = 0
    out_len = 0
    for d in spans:
        before = text[pos : d.start]
        parts.append(before)
        out_len += len(before)
        ph = numbering.get(d.type, text[d.start : d.end])
        parts.append(ph)
        replacements.append(Replacement(d.start, d.end, out_len, out_len + len(ph), ph, d.type, d.source))
        out_len += len(ph)
        pos = d.end
    parts.append(text[pos:])
    # The value put back for a placeholder is its longest mention ("Martin Koch", not "Koch").
    mapping = {ph: max(vals, key=len) for ph, vals in numbering.values.items()}
    return MaskResult("".join(parts), mapping, replacements)


# --- finding placeholders in a model's answer -----------------------------------------

TYPE_ALIASES = {
    "PERSON": ["PERSON", "PERSONS", "NAME", "PER"],
    "EMAIL": ["EMAIL", "E-MAIL", "MAIL", "EMAIL ADDRESS"],
    "PHONE": ["PHONE", "PHONE NUMBER", "TELEFON", "TELEFONNUMMER", "TEL"],
    "IBAN": ["IBAN"],
    "ADDRESS": ["ADDRESS", "ADRESSE", "ANSCHRIFT"],
    "DATE_OF_BIRTH": ["DATE_OF_BIRTH", "DATE OF BIRTH", "DOB", "GEBURTSDATUM", "BIRTHDATE"],
    "CUSTOMER_ID": ["CUSTOMER_ID", "CUSTOMER ID", "CUSTOMER", "KUNDENNUMMER", "ID"],
    "LOCATION": ["LOCATION", "ORT", "LOC"],
}
_ALIAS_TO_TYPE = {}
for _type, _aliases in TYPE_ALIASES.items():
    for _alias in _aliases:
        _ALIAS_TO_TYPE[re.sub(r"[\s_-]", "", _alias)] = _type


def _alias_regex(alias: str) -> str:
    return r"[\s_-]?".join(re.escape(part) for part in re.split(r"[\s_-]", alias))


_ALIASES = sorted({a for aliases in TYPE_ALIASES.values() for a in aliases}, key=len, reverse=True)
_ANY_ALIAS = "|".join(_alias_regex(a) for a in _ALIASES)

STRICT = re.compile(r"\[(?P<type>[A-Z]+(?:_[A-Z]+)*)_(?P<num>\d+)\]")
# Tolerant form: any bracket or none, any case, space / underscore / hyphen / nothing before the number.
ROBUST = re.compile(
    rf"(?P<open>[\[\(\{{<]\s*)?\b(?P<type>{_ANY_ALIAS})(?P<sep>[\s_-]?)(?P<num>\d{{1,3}})\b(?P<close>\s*[\]\)\}}>])?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Found:
    start: int
    end: int
    type: str
    num: int
    exact: bool

    @property
    def placeholder(self) -> str:
        return placeholder(self.type, self.num)


def find_placeholders(text: str) -> list[Found]:
    """Every placeholder-like token in text, exact ones and altered ones.

    An altered form counts only if it has a bracket on at least one side or is written
    with an underscore (PERSON_1): plain prose such as "Person 1" is left alone.
    """
    found = []
    for m in ROBUST.finditer(text):
        if not (m.group("open") or m.group("close") or m.group("sep") == "_"):
            continue
        type_ = _ALIAS_TO_TYPE.get(re.sub(r"[\s_-]", "", m.group("type")).upper())
        if type_ is None:
            continue
        start, end = m.start(), m.end()
        token = m.group()
        exact = STRICT.fullmatch(token) is not None and token == placeholder(type_, int(m.group("num")))
        found.append(Found(start, end, type_, int(m.group("num")), exact))
    return found


def unmask_strict(answer: str, mapping: dict[str, str]) -> str:
    """Put values back only where the placeholder came back exactly as it was sent."""

    def repl(m: re.Match) -> str:
        return mapping.get(m.group(), m.group())

    return STRICT.sub(repl, answer)


def unmask_robust(answer: str, mapping: dict[str, str]) -> str:
    """Put values back for exact and altered placeholders ([Person 1], PERSON1], (PERSON_1) ...)."""
    out = []
    pos = 0
    for f in find_placeholders(answer):
        value = mapping.get(f.placeholder)
        if value is None:
            continue  # invented by the model: nothing to put back
        out.append(answer[pos : f.start])
        out.append(value)
        pos = f.end
    out.append(answer[pos:])
    return "".join(out)
