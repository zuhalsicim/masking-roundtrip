"""The test set: parse the annotated source, build the JSON file, check the manifest."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

TYPES = (
    "PERSON",
    "EMAIL",
    "PHONE",
    "IBAN",
    "ADDRESS",
    "DATE_OF_BIRTH",
    "CUSTOMER_ID",
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ANNOTATED = DATA_DIR / "annotated.txt"
DOCUMENTS = DATA_DIR / "documents.json"
MANIFEST = DATA_DIR / "MANIFEST.sha256"

_HEADER = re.compile(r"^=== (?P<id>[\w-]+) \| (?P<lang>de|en) \| (?P<kind>[\w-]+)\s*$")
_LABEL = re.compile(r"\[\[(?P<type>[A-Z_]+)(?:#(?P<entity>[\w-]+))?:(?P<value>.+?)\]\]")


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    type: str
    text: str
    entity: str


@dataclass
class Document:
    id: str
    lang: str
    kind: str
    text: str
    spans: list[Span] = field(default_factory=list)


def _strip_labels(raw: str, doc_id: str) -> tuple[str, list[Span]]:
    """Remove the [[TYPE:value]] markup and return the plain text with character offsets."""
    out: list[str] = []
    spans: list[Span] = []
    pos = 0
    length = 0
    for m in _LABEL.finditer(raw):
        before = raw[pos : m.start()]
        out.append(before)
        length += len(before)
        value = m.group("value")
        type_ = m.group("type")
        if type_ not in TYPES:
            raise ValueError(f"{doc_id}: unknown type {type_!r}")
        entity = m.group("entity") or value.casefold()
        spans.append(Span(length, length + len(value), type_, value, f"{type_}:{entity}"))
        out.append(value)
        length += len(value)
        pos = m.end()
    out.append(raw[pos:])
    text = "".join(out)
    if "[[" in text or "]]" in text:
        raise ValueError(f"{doc_id}: unbalanced label markup")
    return text, spans


def parse_annotated(source: str) -> list[Document]:
    docs: list[Document] = []
    current: dict | None = None
    lines: list[str] = []

    def flush() -> None:
        if current is None:
            return
        raw = "\n".join(lines).strip("\n")
        text, spans = _strip_labels(raw, current["id"])
        docs.append(Document(current["id"], current["lang"], current["kind"], text, spans))

    for line in source.splitlines():
        header = _HEADER.match(line)
        if header:
            flush()
            current = header.groupdict()
            lines = []
        elif current is None:
            if line.strip() and not line.startswith("#"):
                raise ValueError(f"text before the first document: {line!r}")
        else:
            lines.append(line)
    flush()
    ids = [d.id for d in docs]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate document ids")
    return docs


def to_json(docs: list[Document]) -> str:
    payload = {
        "types": list(TYPES),
        "documents": [
            {**{k: v for k, v in asdict(d).items() if k != "spans"}, "spans": [asdict(s) for s in d.spans]}
            for d in docs
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1) + "\n"


def load_documents(path: Path = DOCUMENTS) -> list[Document]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    docs = []
    for d in payload["documents"]:
        spans = [Span(**s) for s in d["spans"]]
        doc = Document(d["id"], d["lang"], d["kind"], d["text"], spans)
        for s in spans:
            if doc.text[s.start : s.end] != s.text:
                raise ValueError(f"{doc.id}: span {s} does not match the text")
        docs.append(doc)
    return docs


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(annotated: Path = ANNOTATED, documents: Path = DOCUMENTS, manifest: Path = MANIFEST) -> list[Document]:
    """Write documents.json from the annotated source and record both hashes in the manifest."""
    docs = parse_annotated(annotated.read_text(encoding="utf-8"))
    documents.write_bytes(to_json(docs).encode("utf-8"))
    lines = [f"{sha256(p)}  {p.name}" for p in (annotated, documents)]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return docs


def check_manifest(manifest: Path = MANIFEST) -> list[str]:
    """Return the names of files whose hash differs from the manifest (empty list: all good)."""
    bad = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if sha256(manifest.parent / name) != digest:
            bad.append(name)
    return bad


def dataset_version(manifest: Path = MANIFEST) -> str:
    """Short version string: the first 12 hex digits of the hash of documents.json."""
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if name == DOCUMENTS.name:
            return digest[:12]
    raise ValueError("documents.json is not in the manifest")
