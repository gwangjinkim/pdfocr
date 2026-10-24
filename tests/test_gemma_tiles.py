import pytest
from PIL import Image

from pdfocr.gemma_tiles import band_boxes, make_views


def test_odd_sized_page_is_fully_covered_without_blank_padding(tmp_path):
    image = Image.new("RGB", (17, 103))
    image.putdata([(x * 11, y * 2, (x + y) % 256) for y in range(103) for x in range(17)])
    source = tmp_path / "page.png"
    image.save(source)
    result = make_views(source, tmp_path / "views")
    assert result["all_rows_covered"] and len(result["views"]) == 5
    assert result["views"][1]["box"][1] == 0
    assert result["views"][-1]["box"][3] == 103
    for view in result["views"][1:]:
        with Image.open(view["path"]) as crop:
            assert crop.tobytes() == image.crop(view["box"]).tobytes()
    Image.new("RGB", tuple(result["views"][1]["size"]), "white").save(result["views"][1]["path"])
    with pytest.raises(AssertionError):
        make_views(source, tmp_path / "views")


def test_invalid_band_geometry_is_rejected():
    for w, h, count in [(0, 20, 4), (10, 3, 4), (10, 20, 0)]:
        with pytest.raises(ValueError):
            band_boxes(w, h, count)
