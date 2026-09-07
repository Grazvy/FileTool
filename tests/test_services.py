import io

import pytest
from PIL import Image

from backend.errors import ConversionError, PdfError, UnsupportedFormatError
from backend.services import images, loader, pdf


def test_detect_format(png_bytes, jpg_bytes, pdf_bytes):
    assert loader.detect_format(png_bytes) == loader.PNG
    assert loader.detect_format(jpg_bytes) == loader.JPG
    assert loader.detect_format(pdf_bytes) == loader.PDF


def test_detect_format_rejects_other_input():
    with pytest.raises(UnsupportedFormatError):
        loader.detect_format(b"GIF89a not really an image")


@pytest.mark.parametrize("source,target", [("png", "jpg"), ("png", "pdf"), ("jpg", "png"), ("jpg", "pdf")])
def test_supported_conversions(request, source, target):
    data = request.getfixturevalue(f"{source}_bytes")
    result = images.convert(data, source, target)
    assert loader.detect_format(result) == target


def test_png_to_jpg_flattens_transparency():
    transparent = io.BytesIO()
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(transparent, format="PNG")
    result = images.convert(transparent.getvalue(), loader.PNG, loader.JPG)
    assert Image.open(io.BytesIO(result)).convert("RGB").getpixel((0, 0)) == (255, 255, 255)


def test_unsupported_conversion_is_rejected(png_bytes):
    with pytest.raises(ConversionError):
        images.convert(png_bytes, loader.PNG, loader.PNG)


def test_pdf_has_no_conversion_targets():
    assert images.targets_for(loader.PDF) == ()


def test_multi_targets_are_the_ones_that_hold_several_images():
    assert images.multi_targets_for(loader.PNG) == (loader.PDF,)
    assert images.multi_targets_for(loader.PDF) == ()


def test_combine_images_into_one_pdf(png_bytes):
    result = images.combine([png_bytes, png_bytes, png_bytes], loader.PNG, loader.PDF)
    assert pdf.page_count(result) == 3


def test_combine_rejects_several_images_for_a_single_page_target(png_bytes):
    with pytest.raises(ConversionError):
        images.combine([png_bytes, png_bytes], loader.PNG, loader.JPG)


def test_render_previews(pdf_bytes):
    previews = pdf.render_previews(pdf_bytes)
    assert [preview.index for preview in previews] == [0, 1, 2]
    for preview in previews:
        assert loader.detect_format(preview.png) == loader.PNG
        assert preview.width > 0 and preview.height > 0


def test_compose_removes_pages(pdf_bytes):
    assert pdf.page_count(pdf_bytes) == 3
    result = pdf.compose([pdf_bytes], [(0, 0), (0, 2)])
    assert pdf.page_count(result) == 2


def test_compose_reorders_pages(pdf_bytes):
    """The result keeps the requested order, checked through the rendered pixels."""
    original = [_top_left(preview.png) for preview in pdf.render_previews(pdf_bytes)]
    result = pdf.compose([pdf_bytes], [(0, 2), (0, 1), (0, 0)])
    assert [_top_left(preview.png) for preview in pdf.render_previews(result)] == original[::-1]


def test_compose_merges_documents(pdf_bytes):
    result = pdf.compose([pdf_bytes, pdf_bytes], [(0, 0), (1, 1), (1, 2)])
    assert pdf.page_count(result) == 3


def test_compose_rejects_missing_page(pdf_bytes):
    with pytest.raises(PdfError):
        pdf.compose([pdf_bytes], [(0, 7)])


def test_compose_rejects_missing_document(pdf_bytes):
    with pytest.raises(PdfError):
        pdf.compose([pdf_bytes], [(1, 0)])


def test_compose_keeps_at_least_one_page(pdf_bytes):
    with pytest.raises(PdfError):
        pdf.compose([pdf_bytes], [])


def _top_left(png: bytes) -> tuple:
    return Image.open(io.BytesIO(png)).convert("RGB").getpixel((2, 2))


def test_broken_pdf_is_rejected():
    with pytest.raises(PdfError):
        pdf.page_count(b"%PDF-1.4 truncated")
