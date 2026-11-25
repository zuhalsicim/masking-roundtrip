"""Detected spans and how overlapping detections are merged."""

from __future__ import annotations

from dataclasses import dataclass

# When detections overlap, the merged span takes the type of the source with the lower number.
SOURCE_PRIORITY = {"rules": 0, "ner": 1}


@dataclass(frozen=True)
class Detection:
    start: int
    end: int
    type: str
    source: str
    score: float = 1.0


def merge(detections: list[Detection]) -> list[Detection]:
    """Merge overlapping detections into one span that covers all of them.

    Masking more characters never leaks more, so the union is the safe choice. The type
    comes from the highest-priority source, then from the longest detection.
    """
    ordered = sorted(detections, key=lambda d: (d.start, -d.end))
    groups: list[list[Detection]] = []
    group_end = -1
    for d in ordered:
        if groups and d.start < group_end:
            groups[-1].append(d)
            group_end = max(group_end, d.end)
        else:
            groups.append([d])
            group_end = d.end
    merged = []
    for g in groups:
        best = min(g, key=lambda d: (SOURCE_PRIORITY.get(d.source, 9), -(d.end - d.start)))
        start = min(d.start for d in g)
        end = max(d.end for d in g)
        sources = "+".join(sorted({d.source for d in g}, key=lambda s: SOURCE_PRIORITY.get(s, 9)))
        merged.append(Detection(start, end, best.type, sources, best.score))
    return merged
