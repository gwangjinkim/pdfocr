from pdfocr.book_compare import content_text, rates


def test_content_policy_preserves_spelling_and_interpage_hyphen():
    assert (
        content_text("— 5 —\n\n**Kränklich-\nkeit** und anstecken-")
        == "Kränklichkeit und anstecken-"
    )
    assert content_text("ſo\n\n— Gewiß!") == "so — Gewiß!"
    assert rates("Armuth", "Armut")["character_edits"] == 1


def test_internal_number_is_not_removed():
    assert content_text("vor 10 Jahren und 10,000 Arme") == "vor 10 Jahren und 10,000 Arme"
