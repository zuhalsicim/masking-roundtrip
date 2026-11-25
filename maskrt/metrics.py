"""Scoring detections against the hand labels.

Definitions (also in the README):
- A labelled span is *protected* when every non-space character of it is masked.
  Otherwise it *leaks*: at least part of the value reaches the model.
- Recall of a type = protected spans / labelled spans of that type (= 1 - leakage).
- A detection is *correct* when at least half of its non-space characters lie inside
  labelled spans. Precision of a type = correct detections / detections of that type.
  A wrong detection is over-masking: it hides text the model may need, but leaks nothing.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass

from .dataset import Document, Span
from .spans import Detection, merge


def _covered(length: int, intervals: list[tuple[int, int]]) -> list[bool]:
    mask = [False] * length
    for s, e in intervals:
        for i in range(max(0, s), min(length, e)):
            mask[i] = True
    return mask


def span_protected(text: str, span: Span, covered: list[bool]) -> bool:
    return all(covered[i] for i in range(span.start, span.end) if not text[i].isspace())


def detection_correct(text: str, det: Detection, gold: list[bool]) -> bool:
    chars = [i for i in range(det.start, det.end) if not text[i].isspace()]
    if not chars:
        return False
    return sum(gold[i] for i in chars) * 2 >= len(chars)


@dataclass
class DocScore:
    doc_id: str
    lang: str
    spans: list[tuple[Span, bool]]  # (labelled span, protected?)
    detections: list[tuple[Detection, bool]]  # (merged detection, correct?)

    @property
    def leaked(self) -> int:
        return sum(not ok for _, ok in self.spans)


def score_document(doc: Document, detections: list[Detection]) -> DocScore:
    merged = merge(detections)
    covered = _covered(len(doc.text), [(d.start, d.end) for d in merged])
    gold = _covered(len(doc.text), [(s.start, s.end) for s in doc.spans])
    spans = [(s, span_protected(doc.text, s, covered)) for s in doc.spans]
    dets = [(d, detection_correct(doc.text, d, gold)) for d in merged]
    return DocScore(doc.id, doc.lang, spans, dets)


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


def bootstrap(scores: list[DocScore], stat, n: int = 2000, seed: int = 0) -> tuple[float, float]:
    """Percentile 95 % interval of stat(sample) over documents drawn with replacement."""
    rng = random.Random(seed)
    values = []
    for _ in range(n):
        sample = [scores[rng.randrange(len(scores))] for _ in scores]
        v = stat(sample)
        if v is not None:
            values.append(v)
    values.sort()
    lo = values[int(0.025 * (len(values) - 1))]
    hi = values[int(0.975 * (len(values) - 1))]
    return lo, hi


def leak_rate(scores: list[DocScore]) -> float | None:
    return _ratio(sum(s.leaked for s in scores), sum(len(s.spans) for s in scores))


def docs_with_leak_rate(scores: list[DocScore]) -> float | None:
    return _ratio(sum(s.leaked > 0 for s in scores), len(scores))


def summarise(scores: list[DocScore], n_boot: int = 2000, seed: int = 0) -> dict:
    """All numbers for one detector: leakage with intervals, recall and precision per type and language."""
    total_spans = sum(len(s.spans) for s in scores)
    leaked = sum(s.leaked for s in scores)
    docs_leaking = sum(s.leaked > 0 for s in scores)
    out: dict = {
        "documents": len(scores),
        "labelled_spans": total_spans,
        "leaked_spans": leaked,
        "leak_rate": leak_rate(scores),
        "leak_rate_ci95": bootstrap(scores, leak_rate, n_boot, seed),
        "documents_with_leak": docs_leaking,
        "documents_with_leak_rate": docs_with_leak_rate(scores),
        "documents_with_leak_rate_ci95": bootstrap(scores, docs_with_leak_rate, n_boot, seed),
    }

    recall: dict = defaultdict(lambda: [0, 0])  # key -> [protected, labelled]
    precision: dict = defaultdict(lambda: [0, 0])  # key -> [correct, detected]
    for s in scores:
        for span, ok in s.spans:
            for key in (span.type, f"{span.type}|{s.lang}", f"ALL|{s.lang}", "ALL"):
                recall[key][0] += ok
                recall[key][1] += 1
        for det, ok in s.detections:
            for key in (det.type, f"{det.type}|{s.lang}", f"ALL|{s.lang}", "ALL"):
                precision[key][0] += ok
                precision[key][1] += 1
    out["recall"] = {k: {"protected": v[0], "labelled": v[1], "recall": _ratio(*v)} for k, v in sorted(recall.items())}
    out["precision"] = {
        k: {"correct": v[0], "detected": v[1], "precision": _ratio(*v)} for k, v in sorted(precision.items())
    }
    out["leaks"] = [
        {"doc": s.doc_id, "type": span.type, "text": span.text} for s in scores for span, ok in s.spans if not ok
    ]
    out["over_masked"] = [
        {"doc": s.doc_id, "type": d.type, "start": d.start, "end": d.end}
        for s in scores
        for d, ok in s.detections
        if not ok
    ]
    return out


def consistency(doc: Document, replacements) -> dict:
    """Do all mentions of one labelled person get one placeholder, and different people different ones?

    Looks only at labelled PERSON mentions that are fully inside one replacement.
    split: one labelled person got two or more placeholders.
    merged: one placeholder stands for two or more labelled people.
    """
    by_entity: dict[str, set[str]] = defaultdict(set)
    by_placeholder: dict[str, set[str]] = defaultdict(set)
    for span in doc.spans:
        if span.type != "PERSON":
            continue
        for r in replacements:
            if r.start <= span.start and span.end <= r.end:
                by_entity[span.entity].add(r.placeholder)
                by_placeholder[r.placeholder].add(span.entity)
                break
    multi = {e: phs for e, phs in by_entity.items() if sum(1 for s in doc.spans if s.entity == e) > 1}
    return {
        "people_with_several_mentions": len(multi),
        "split": sorted(e for e, phs in multi.items() if len(phs) > 1),
        "merged": sorted(ph for ph, ents in by_placeholder.items() if len(ents) > 1),
    }
