"""Markdown tables for the README, printed from the result files (nothing is typed in by hand)."""

from __future__ import annotations

import json
from pathlib import Path

from .dataset import TYPES


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f} %"


def _ci(ci) -> str:
    return f"{100 * ci[0]:.1f} to {100 * ci[1]:.1f} %"


def detection_tables(results: Path) -> str:
    path = results / "detection.json"
    if not path.exists():
        return "(no results/detection.json yet)"
    det = json.loads(path.read_text(encoding="utf-8"))["detectors"]
    names = list(det)
    lines = ["### Leakage", "",
             "| Detector | Labelled spans that leak | Leak rate (95 % interval) "
             "| Documents with a leak (95 % interval) | Over-masked spans | ms per document (median) |",
             "|---|---|---|---|---|---|"]
    for n in names:
        s = det[n]
        over = len(s["over_masked"])
        lines.append(
            f"| {n} | {s['leaked_spans']} of {s['labelled_spans']} "
            f"| {_pct(s['leak_rate'])} ({_ci(s['leak_rate_ci95'])}) "
            f"| {s['documents_with_leak']} of {s['documents']} ({_ci(s['documents_with_leak_rate_ci95'])}) "
            f"| {over} of {s['precision']['ALL']['detected']} | {s['speed_per_document']['median_ms']:.2f} |"
        )
    lines += ["", "### Recall per type (labelled spans fully masked)", "",
              "| Type | Labelled | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    for t in TYPES:
        row = [t, str(det[names[0]]["recall"].get(t, {}).get("labelled", 0))]
        for n in names:
            r = det[n]["recall"].get(t)
            row.append("n/a" if r is None else f"{r['protected']} ({_pct(r['recall'])})")
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "### Per language", "",
              "| Language | Detector | Recall | Precision |", "|---|---|---|---|"]
    for lang in ("de", "en"):
        for n in names:
            r = det[n]["recall"].get(f"ALL|{lang}")
            p = det[n]["precision"].get(f"ALL|{lang}")
            rtxt = f"{r['protected']}/{r['labelled']} ({_pct(r['recall'])})" if r else "n/a"
            ptxt = f"{p['correct']}/{p['detected']} ({_pct(p['precision'])})" if p else "n/a"
            lines.append(f"| {lang} | {n} | {rtxt} | {ptxt} |")
    lines += ["", "### Precision per detected type", "",
              "| Detector | Type | Correct / detected | Precision |", "|---|---|---|---|"]
    for n in names:
        for k, p in det[n]["precision"].items():
            if "|" in k or k == "ALL":
                continue
            lines.append(f"| {n} | {k} | {p['correct']}/{p['detected']} | {_pct(p['precision'])} |")
    lines += ["", "### Same person, same placeholder", "",
              "| Detector | People with several mentions | Split (one person, several placeholders) "
              "| Merged (one placeholder, several people) |", "|---|---|---|---|"]
    for n in names:
        c = det[n]["consistency"]
        split = ", ".join(c["split"]) or "none"
        merged = ", ".join(c["merged"]) or "none"
        lines.append(f"| {n} | {c['people_with_several_mentions']} | {split} | {merged} |")
    return "\n".join(lines)


def roundtrip_tables(results: Path) -> str:
    path = results / "roundtrip.json"
    if not path.exists():
        return "(no results/roundtrip.json yet)"
    rt = json.loads(path.read_text(encoding="utf-8"))
    lines = ["### Placeholders in the model's answers", "",
             "| Prompt | Answers | Placeholder tokens in answers | Exact | Altered | Invented "
             "| Answers fully restored, strict unmasking | Answers fully restored, robust unmasking |",
             "|---|---|---|---|---|---|---|---|"]
    for v, s in rt["summary"].items():
        lines.append(
            f"| {v} | {s['answers']} | {s['placeholder_tokens_in_answers']} | {s['exact']} ({_pct(s['exact_share'])}) "
            f"| {s['altered']} ({_pct(s['altered_share'])}) | {s['invented']} ({_pct(s['invented_share'])}) "
            f"| {s['answers_fully_restored_strict']} ({_pct(s['answers_fully_restored_strict_share'])}) "
            f"| {s['answers_fully_restored_robust']} ({_pct(s['answers_fully_restored_robust_share'])}) |"
        )
    forms: dict[str, int] = {}
    for r in rt["answers"]:
        for f in r["altered_forms"]:
            forms[f] = forms.get(f, 0) + 1
    if forms:
        top = sorted(forms.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
        lines += ["", "Altered forms seen (answers containing them): "
                  + ", ".join(f"`{f}` ({c})" for f, c in top)]
    return "\n".join(lines)
