from pdfocr.gemma_format import unwrap_presentation


def test_removes_only_a_contiguous_presentation_prefix_and_suffix():
    raw = "```markdown\n# Transcription of Page 10\n\n---\n\n- 10 -\n\nkeit widmen.\n\n*) A real footnote.\n```"
    result = unwrap_presentation(raw)
    assert result["markdown"] == "keit widmen.\n\n*) A real footnote."
    assert result["markdown"] == raw[result["source_start"] : result["source_end"]]


def test_body_spelling_hyphens_and_page_mentions_are_untouched():
    raw = "Per-\n\nPage 5 is mentioned in the body.\n# Page 6\nson."
    assert unwrap_presentation(raw)["markdown"] == raw


def test_does_not_treat_multiple_code_blocks_as_one_outer_wrapper():
    raw = "```markdown\nbody\n```\n\n```text\nmore\n```"
    assert unwrap_presentation(raw)["markdown"] == raw
