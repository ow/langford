from pipeline.ingestion.image_extractor import (
    _looks_like_margin_decoration,
    assign_images_by_number,
    is_junk_image,
)


def test_teleconference_description_is_junk():
    assert is_junk_image("Meeting available by teleconference using Zoom")


def test_small_wide_top_margin_image_is_decoration():
    assert _looks_like_margin_decoration(
        400,
        123,
        {"x0": 100, "y0": 22, "x1": 500, "y1": 80},
        page_height=792,
    )


def test_large_map_near_top_is_not_decoration():
    assert not _looks_like_margin_decoration(
        900,
        620,
        {"x0": 60, "y0": 40, "x1": 560, "y1": 690},
        page_height=792,
    )


def test_assign_images_by_number_drops_junk_reference_and_keeps_map():
    sections = [
        {
            "section_id": 10,
            "section_text": (
                "[Image 1: Meeting available by teleconference]\n"
                "[Image 2: Site map showing proposed lot layout]"
            ),
        }
    ]
    images = [
        {
            "xref": 1,
            "page": 1,
            "width": 400,
            "height": 123,
            "bbox": {"x0": 100, "y0": 22, "x1": 500, "y1": 80},
        },
        {
            "xref": 2,
            "page": 2,
            "width": 900,
            "height": 620,
            "bbox": {"x0": 60, "y0": 120, "x1": 560, "y1": 690},
        },
    ]

    kept = assign_images_by_number(sections, images)

    assert len(kept) == 1
    assert kept[0]["xref"] == 2
    assert kept[0]["section_id"] == 10
    assert kept[0]["description"] == "Site map showing proposed lot layout"
