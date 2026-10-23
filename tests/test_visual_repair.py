from pdfocr.visual_repair import evidence_gate, remove_boundary_separators


def test_requires_visible_hyphen_matching_words_and_adjacent_pages():
    good = dict(
        left_page=9,
        right_page=10,
        left_ocr="die anstecken",
        right_ocr="den aufspürt",
        visual_left="Keime der anstecken-",
        visual_right="den aufspürt",
    )
    assert evidence_gate(**good)["eligible"]
    assert not evidence_gate(**{**good, "visual_left": "Keime der anstecken"})["eligible"]
    assert not evidence_gate(**{**good, "left_ocr": "die Krankheiten"})["eligible"]
    assert not evidence_gate(**{**good, "right_page": 11})["eligible"]
    assert not evidence_gate(**{**good, "visual_right": "Der Arzt"})["eligible"]
    assert not evidence_gate(
        **{**good, "right_ocr": "und der Arzt", "visual_right": "und der Arzt"}
    )["eligible"]


def test_remove_only_a_mapped_interpage_separator():
    raw = "anstecken|den"
    text = "anstecken den"
    spans = [
        dict(kind="source", page=9, output_start=0, output_end=9, raw_start=0, raw_end=9),
        dict(kind="separator", output_start=9, output_end=10),
        dict(kind="source", page=10, output_start=10, output_end=13, raw_start=10, raw_end=13),
    ]
    result = remove_boundary_separators(
        text,
        {
            "spans": spans,
            "boundaries": [{"output_offset": 10}],
            "relocations": [{"output_start": 10, "output_end": 13}],
        },
        [(9, 10)],
    )
    assert result["text"] == "ansteckenden"
    assert result["map"]["boundaries"][0]["output_offset"] == 9
    assert result["map"]["relocations"][0] == {"output_start": 9, "output_end": 12}
    for span in result["map"]["spans"]:
        if span["kind"] == "source":
            assert (
                result["text"][span["output_start"] : span["output_end"]]
                == raw[span["raw_start"] : span["raw_end"]]
            )
    # Reject a separator if the model moved unrelated text between the pages.
    spans.insert(
        2, dict(kind="source", page=9, output_start=10, output_end=10, raw_start=0, raw_end=0)
    )
    assert remove_boundary_separators(text, {"spans": spans}, [(9, 10)])["text"] == text


def test_fraktur_repair_accepts_long_s_but_never_replaces_misread_letters():
    case = dict(
        left_page=34,
        right_page=35,
        left_ocr="alles in einer Per",
        right_ocr="son. Seine Reputation",
        visual_left="alles in einer Per-",
        visual_right="ſon. Seine Reputation",
    )
    assert evidence_gate(**case)["eligible"]
    # Observed GLM visual error must not authorize replacing j with s.
    assert not evidence_gate(**{**case, "visual_right": "jon. Seine Reputation"})["eligible"]
    # Observed Ovis/Paddle-200 page error cannot be repaired by deleting a space.
    assert not evidence_gate(**{**case, "right_ocr": "ion. Seine Reputation"})["eligible"]
    assert not evidence_gate(**{**case, "visual_left": "alles in einer Per"})["eligible"]
