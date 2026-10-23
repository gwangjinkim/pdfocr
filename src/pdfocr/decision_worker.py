from __future__ import annotations

import json
import sys
from pathlib import Path

from .borrowed.archive_stitching import Page, PageStitcher
from .repair import DecisionBackend, MLXDecisionBackend
from .util import write_json


def main(request: dict) -> None:
    backend = (
        MLXDecisionBackend(request["model_path"])
        if request["backend"] == "mlx"
        else DecisionBackend(request["model_name"], request["endpoint"])
    )
    stitcher = PageStitcher(backend, running_headers=request.get("running_headers", []))
    if request["task"] == "repair":
        stitcher.process(request["raw"], request["output"], request["report"])
    else:
        results = []
        rows = [
            json.loads(s) for s in Path(request["dataset"]).read_text().splitlines() if s.strip()
        ]
        for row in rows:
            if row.get("split") != request["split"]:
                continue
            decision = stitcher.decide(
                Page(row.get("left_page", 1), row["left"], row.get("left_error", False)),
                Page(row.get("right_page", 2), row["right"], row.get("right_error", False)),
                right_header=row.get("header", ""),
                left_note=row.get("left_note", ""),
            )
            results.append(
                {
                    "id": row["id"],
                    "expected": row["expected_action"],
                    "origin": row.get("origin"),
                    "decision": decision,
                }
            )
        joined = {"join_word", "join_space", "keep_hyphen", "drop_catchword"}
        applied = [r for r in results if r["decision"]["action"] in joined]
        good = sum(r["decision"]["action"] == r["expected"] for r in applied)
        summary = {
            "cases": len(results),
            "action_accuracy": sum(r["decision"]["action"] == r["expected"] for r in results)
            / len(results)
            if results
            else None,
            "applied_joins": len(applied),
            "correct_applied_joins": good,
            "join_precision": good / len(applied) if applied else None,
            "wrong_applied_joins": len(applied) - good,
            "deferred": sum(r["decision"]["action"] == "uncertain" for r in results),
            "caveat": "Reused archiveorgocr regression cases and provisional labels. Not a blind generalization test; no fine-tuning performed.",
            "results": results,
        }
        write_json(Path(request["output"]), summary)


if __name__ == "__main__":
    main(json.loads(Path(sys.argv[1]).read_text()))
