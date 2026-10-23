from pdfocr.paddle_book import assemble_book


def test_book_mode_retains_footnote_and_removes_cross_label_duplicate():
    blocks = [
        {"label": "text", "score": 0.7, "bbox": [0, 0, 100, 100], "text": "body"},
        {"label": "algorithm", "score": 0.6, "bbox": [0, 0, 100, 100], "text": "body duplicate"},
        {"label": "footnote", "score": 0.8, "bbox": [0, 110, 100, 130], "text": "*) note"},
        {"label": "number", "score": 0.9, "bbox": [50, 0, 60, 5], "text": "12"},
    ]
    value = assemble_book(blocks)
    assert value["markdown"] == "body\n\n*) note"
    assert value["kept_indices"] == [0, 2]


def test_small_nested_caption_is_not_a_duplicate_of_large_region():
    blocks = [
        {"label": "text", "score": 0.9, "bbox": [0, 0, 100, 100], "text": "body"},
        {"label": "paragraph_title", "score": 0.8, "bbox": [10, 10, 90, 20], "text": "title"},
    ]
    assert assemble_book(blocks)["kept_indices"] == [0, 1]
