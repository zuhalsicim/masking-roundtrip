"""Command line: python -m maskrt <step>."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from . import dataset, pipeline, report


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="maskrt", description="Masking round trip: detect, mask, model, unmask, measure.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build-data", help="data/annotated.txt -> data/documents.json and data/MANIFEST.sha256")
    sub.add_parser("check-data", help="check the data files against data/MANIFEST.sha256")
    d = sub.add_parser("detect", help="run the detectors and score them -> results/detection.json")
    d.add_argument("--detectors", default=",".join(pipeline.DETECTORS))
    m = sub.add_parser("model", help="send the masked texts to the model -> results/answers.json")
    m.add_argument("--limit", type=int, default=None, help="only the first N documents")
    m.add_argument("--variants", default="plain,instructed")
    m.add_argument("--max-new-tokens", type=int, default=160)
    m.add_argument("--threads", type=int, default=None, help="llama.cpp threads (default: its own choice)")
    sub.add_parser("analyse", help="placeholder survival and unmasking -> results/roundtrip.json")
    sub.add_parser("export", help="results/viewer.json for the web page")
    sub.add_parser("tables", help="print the README tables from the result files")
    a = sub.add_parser("all", help="detect, model, analyse, export, tables")
    a.add_argument("--limit", type=int, default=None)
    sub.add_parser("smoke", help="CI check without any model (rules only, temporary output)")
    args = p.parse_args(argv)

    if args.cmd == "build-data":
        docs = dataset.build()
        print(f"{len(docs)} documents, {sum(len(x.spans) for x in docs)} labelled spans, "
              f"version {dataset.dataset_version()}")
    elif args.cmd == "check-data":
        bad = dataset.check_manifest()
        if bad:
            raise SystemExit(f"changed: {', '.join(bad)}")
        print(f"data files match the manifest (version {dataset.dataset_version()})")
    elif args.cmd == "detect":
        pipeline.run_detection(tuple(args.detectors.split(",")))
        print(report.detection_tables(pipeline.RESULTS))
    elif args.cmd == "model":
        pipeline.run_model(variants=tuple(args.variants.split(",")), limit=args.limit,
                           max_new_tokens=args.max_new_tokens, threads=args.threads)
    elif args.cmd == "analyse":
        pipeline.run_analysis()
        print(report.roundtrip_tables(pipeline.RESULTS))
    elif args.cmd == "export":
        pipeline.run_export()
    elif args.cmd == "tables":
        print(report.detection_tables(pipeline.RESULTS))
        print(report.roundtrip_tables(pipeline.RESULTS))
    elif args.cmd == "all":
        pipeline.run_detection()
        pipeline.run_model(limit=args.limit)
        pipeline.run_analysis()
        pipeline.run_export()
        print(report.detection_tables(pipeline.RESULTS))
        print(report.roundtrip_tables(pipeline.RESULTS))
    elif args.cmd == "smoke":
        with tempfile.TemporaryDirectory() as tmp:
            s = pipeline.smoke(Path(tmp))
        print(f"smoke ok: rules leak {s['leaked_spans']}/{s['labelled_spans']} labelled spans")


if __name__ == "__main__":
    main()
