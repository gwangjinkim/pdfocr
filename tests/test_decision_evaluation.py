import json
from unittest.mock import patch

from pdfocr.decision_worker import main


def test_evaluator_preserves_source_page_numbers_errors_and_notes(tmp_path):
    data = tmp_path / "cases.jsonl"
    data.write_text(
        json.dumps(
            {
                "id": "gap",
                "split": "test",
                "left": "ent-",
                "right": "wicklung",
                "left_page": 7,
                "right_page": 9,
                "left_error": True,
                "left_note": "exact note",
                "expected_action": "keep",
            }
        )
        + "\n"
    )
    output = tmp_path / "results.json"
    with (
        patch("pdfocr.decision_worker.MLXDecisionBackend"),
        patch("pdfocr.decision_worker.PageStitcher") as s,
    ):
        s.return_value.decide.return_value = {"action": "keep"}
        main(
            {
                "backend": "mlx",
                "model_path": "unused",
                "task": "evaluate",
                "dataset": str(data),
                "split": "test",
                "output": str(output),
            }
        )
        args, kwargs = s.return_value.decide.call_args
        assert args[0].number == 7 and args[0].error
        assert args[1].number == 9
        assert kwargs["left_note"] == "exact note"
