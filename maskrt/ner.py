"""Detector (b): open NER models on CPU (spaCy), for names and places.

Two variants:
- ner_multi: xx_ent_wiki_sm, one model for any language.
- ner_lang:  de_core_news_sm for German, en_core_web_sm for English. It is told the
             language of the document (from the test set), so it skips language detection.
"""

from __future__ import annotations

import os
from pathlib import Path

from .spans import Detection

MODELS_DIR = Path(os.environ.get("MASKRT_MODELS", Path(__file__).resolve().parent.parent / "models"))

SPACY_MODELS = {
    "multi": "xx_ent_wiki_sm",
    "de": "de_core_news_sm",
    "en": "en_core_web_sm",
}
SPACY_MODEL_VERSION = "3.8.0"

# PER and LOC are masked. ORG is not: company names are not personal data in this test set.
LABEL_MAP = {"PER": "PERSON", "PERSON": "PERSON", "LOC": "LOCATION", "GPE": "LOCATION", "FAC": "LOCATION"}


def model_path(name: str) -> Path:
    return MODELS_DIR / "spacy" / f"{name}-{SPACY_MODEL_VERSION}"


def _load(name: str):
    import spacy

    nlp = spacy.load(model_path(name))
    keep = {"ner"} | {n for n in ("tok2vec",) if n in nlp.pipe_names}
    nlp.select_pipes(enable=[n for n in nlp.pipe_names if n in keep])
    return nlp


def model_meta(name: str) -> dict:
    nlp = _load(name)
    return {k: nlp.meta.get(k) for k in ("name", "lang", "version", "license", "spacy_version")}


def split_at_newlines(start: int, end: int, text: str) -> list[tuple[int, int]]:
    """A name does not run across a line break: cut an entity into its lines.

    The small models sometimes join "Grace Baker" and "- Will" on the next line into one
    entity; masked as one placeholder, two people would share it.
    """
    parts = []
    pos = start
    for line in text[start:end].split("\n"):
        s, e = pos, pos + len(line)
        while s < e and not text[s].isalnum():
            s += 1
        while e > s and not text[e - 1].isalnum() and text[e - 1] not in ".'":
            e -= 1
        if e > s:
            parts.append((s, e))
        pos += len(line) + 1
    return parts


def _entities(nlp, text: str, source: str) -> list[Detection]:
    found = []
    for ent in nlp(text).ents:
        type_ = LABEL_MAP.get(ent.label_)
        if type_ is None:
            continue
        for s, e in split_at_newlines(ent.start_char, ent.end_char, text):
            found.append(Detection(s, e, type_, source))
    return found


class MultiNer:
    """xx_ent_wiki_sm for every document."""

    def __init__(self) -> None:
        self.nlp = _load(SPACY_MODELS["multi"])

    def __call__(self, text: str, lang: str) -> list[Detection]:
        return _entities(self.nlp, text, "ner")


class LangNer:
    """One spaCy model per language, chosen by the document's language."""

    def __init__(self) -> None:
        self.nlps = {lang: _load(SPACY_MODELS[lang]) for lang in ("de", "en")}

    def __call__(self, text: str, lang: str) -> list[Detection]:
        return _entities(self.nlps[lang], text, "ner")
