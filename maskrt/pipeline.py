"""The steps of the experiment. Each step reads and writes JSON in results/."""

from __future__ import annotations

import json
import os
import platform
import statistics
import time
from dataclasses import asdict
from pathlib import Path

from . import dataset
from .masking import mask
from .metrics import consistency, score_document, summarise
from .rules import detect_rules
from .spans import Detection
from .survival import analyse_answer, summarise_survival

RESULTS = Path(__file__).resolve().parent.parent / "results"
DETECTORS = ("rules", "ner_multi", "ner_lang", "combined")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def environment() -> dict:
    import importlib.metadata as md

    versions = {}
    for pkg in ("spacy",):
        try:
            versions[pkg] = md.version(pkg)
        except md.PackageNotFoundError:
            pass
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "packages": versions,
    }


def _timed(fn, text: str, lang: str, repeats: int) -> tuple[list[Detection], float]:
    """Run fn repeats times; return its result and the median milliseconds."""
    times = []
    result: list[Detection] = []
    for _ in range(repeats):
        t = time.perf_counter()
        result = fn(text, lang)
        times.append((time.perf_counter() - t) * 1000)
    return result, statistics.median(times)


def _speed(ms: list[float]) -> dict:
    ordered = sorted(ms)
    return {
        "mean_ms": round(statistics.mean(ms), 3),
        "median_ms": round(statistics.median(ms), 3),
        "max_ms": round(ordered[-1], 3),
    }


def run_detection(
    detectors: tuple[str, ...] = DETECTORS, out: Path = RESULTS, repeats: int = 5, n_boot: int = 2000
) -> dict:
    bad = dataset.check_manifest()
    if bad:
        raise SystemExit(f"data files differ from data/MANIFEST.sha256: {bad}")
    docs = dataset.load_documents()
    fns = {"rules": lambda text, lang: detect_rules(text)}
    ner_info = None
    if set(detectors) - {"rules"}:
        from .ner import SPACY_MODELS, LangNer, MultiNer, model_meta

        multi, per_lang = MultiNer(), LangNer()
        for lang in ("de", "en"):  # warm-up
            multi("Anna Beispiel wohnt in Berlin.", lang)
            per_lang("Anna Beispiel wohnt in Berlin.", lang)
        fns["ner_multi"] = multi
        fns["ner_lang"] = per_lang
        fns["combined"] = lambda text, lang: detect_rules(text) + multi(text, lang) + per_lang(text, lang)
        ner_info = {name: model_meta(name) for name in SPACY_MODELS.values()}

    per_detector = {}
    per_doc = {d.id: {"id": d.id, "lang": d.lang, "kind": d.kind, "text": d.text,
                      "spans": [asdict(s) for s in d.spans], "detectors": {}} for d in docs}
    for name in detectors:
        scores, times, splits, merges, several = [], [], [], [], 0
        for doc in docs:
            found, ms = _timed(fns[name], doc.text, doc.lang, repeats)
            times.append(ms)
            score = score_document(doc, found)
            scores.append(score)
            masked = mask(doc.text, found)
            cons = consistency(doc, masked.replacements)
            several += cons["people_with_several_mentions"]
            splits += [f"{doc.id}:{e}" for e in cons["split"]]
            merges += [f"{doc.id}:{p}" for p in cons["merged"]]
            per_doc[doc.id]["detectors"][name] = {
                "masked": masked.masked,
                "mapping": masked.mapping,
                "replacements": [asdict(r) for r in masked.replacements],
                "leaked": [s.text for s, ok in score.spans if not ok],
                "ms": round(ms, 3),
            }
        summary = summarise(scores, n_boot=n_boot)
        summary["speed_per_document"] = _speed(times)
        summary["consistency"] = {
            "people_with_several_mentions": several,
            "split": splits,
            "merged": merges,
        }
        per_detector[name] = summary

    payload = {
        "dataset_version": dataset.dataset_version(),
        "environment": environment(),
        "ner_model": ner_info,
        "timing": f"median of {repeats} runs per document, milliseconds, after one warm-up call",
        "bootstrap": {"resamples": n_boot, "seed": 0, "unit": "document", "interval": "percentile 95 %"},
        "detectors": per_detector,
        "documents": list(per_doc.values()),
    }
    _write(out / "detection.json", payload)
    return payload


def run_model(
    out: Path = RESULTS,
    variants: tuple[str, ...] = ("plain", "instructed"),
    detector: str = "combined",
    limit: int | None = None,
    max_new_tokens: int = 160,
    threads: int | None = None,
) -> dict:
    from . import llm

    det = _read(out / "detection.json")
    docs = det["documents"][:limit] if limit else det["documents"]
    answers = []
    t0 = time.perf_counter()
    with llm.LlamaServer(threads=threads) as server:
        load_s = time.perf_counter() - t0
        for variant in variants:
            for i, d in enumerate(docs, 1):
                prompt = llm.PROMPTS[variant].format(text=d["detectors"][detector]["masked"])
                r = server.chat(prompt, max_new_tokens)
                r.update({"id": d["id"], "variant": variant,
                          "hit_token_limit": r["finish_reason"] == "length"})
                answers.append(r)
                print(f"{variant} {i}/{len(docs)} {d['id']}: {r['seconds']:.1f} s", flush=True)
    gen_s = sum(a["seconds"] for a in answers)
    new_tokens = sum(a["new_tokens"] or 0 for a in answers)
    payload = {
        "dataset_version": det["dataset_version"],
        "environment": environment(),
        "model": {"name": llm.LLM_NAME, "file": llm.GGUF_FILE, "sha256": llm.GGUF_SHA256,
                  "source": llm.GGUF_SOURCE, "license": llm.LLM_LICENSE,
                  "runtime": f"llama.cpp llama-server {llm.LLAMA_CPP_VERSION}, CPU, one request at a time"},
        "decoding": {"temperature": 0, "top_k": 1, "seed": 0, "max_new_tokens": max_new_tokens},
        "input": f"texts masked by the '{detector}' detector",
        "prompts": {v: llm.PROMPTS[v] for v in variants},
        "server_start_seconds": round(load_s, 1),
        "wall_seconds_all_answers": round(gen_s, 1),
        "seconds_per_answer_mean": round(gen_s / len(answers), 2) if answers else None,
        "new_tokens": new_tokens,
        "answers": answers,
    }
    _write(out / "answers.json", payload)
    return payload


def run_analysis(out: Path = RESULTS, detector: str = "combined") -> dict:
    det = _read(out / "detection.json")
    ans = _read(out / "answers.json")
    docs = {d["id"]: d for d in det["documents"]}
    rows_by_variant: dict[str, list[dict]] = {}
    for a in ans["answers"]:
        d = docs[a["id"]]["detectors"][detector]
        row = analyse_answer(a["answer"], d["mapping"], d["leaked"])
        row.update({"id": a["id"], "variant": a["variant"], "answer": a["answer"]})
        rows_by_variant.setdefault(a["variant"], []).append(row)
    payload = {
        "dataset_version": det["dataset_version"],
        "model": ans["model"],
        "summary": {v: summarise_survival(rows) for v, rows in rows_by_variant.items()},
        "answers": [r for rows in rows_by_variant.values() for r in rows],
    }
    _write(out / "roundtrip.json", payload)
    return payload


def run_export(out: Path = RESULTS, detector: str = "combined") -> dict:
    """One small file for the web page: every document with the four texts and the spans."""
    det = _read(out / "detection.json")
    rt = _read(out / "roundtrip.json") if (out / "roundtrip.json").exists() else {"answers": []}
    by_id: dict[str, dict] = {}
    for r in rt["answers"]:
        by_id.setdefault(r["id"], {})[r["variant"]] = {
            "answer": r["answer"],
            "restored_strict": r["restored_strict"],
            "restored_robust": r["restored_robust"],
            "altered_forms": r["altered_forms"],
            "invented_forms": r["invented_forms"],
        }
    docs = []
    for d in det["documents"]:
        m = d["detectors"][detector]
        docs.append({
            "id": d["id"], "lang": d["lang"], "kind": d["kind"], "text": d["text"],
            "spans": [{k: s[k] for k in ("start", "end", "type")} for s in d["spans"]],
            "masked": m["masked"], "mapping": m["mapping"],
            "replacements": [{k: r[k] for k in ("start", "end", "masked_start", "masked_end", "placeholder", "source")}
                             for r in m["replacements"]],
            "leaked": m["leaked"],
            "answers": by_id.get(d["id"], {}),
        })
    payload = {"dataset_version": det["dataset_version"], "detector": detector, "documents": docs}
    _write(out / "viewer.json", payload)
    return payload


def smoke(out: Path) -> dict:
    """The CI check without any model: rules only, and a made-up model answer through unmasking."""
    payload = run_detection(detectors=("rules",), out=out, repeats=1, n_boot=200)
    doc = payload["documents"][0]["detectors"]["rules"]
    ph = next(iter(doc["mapping"]))
    fake = f"Summary: {ph} wrote; also {ph.replace('_', ' ').title()} and [PERSON_99]."
    row = analyse_answer(fake, doc["mapping"], [])
    assert row["exact"] == 1 and row["altered"] == 1 and row["invented"] == 1, row
    assert row["left_after_robust"] == 1, row
    return payload["detectors"]["rules"]
