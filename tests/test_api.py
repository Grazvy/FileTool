from backend.services import loader, pdf


def test_health(client):
    # "app" tells the page whether it can offer to stop the app; see test_handoff.
    assert client.get("/api/health").json() == {"status": "ok", "app": False}


def test_load_image_offers_conversion_targets(client, png_bytes):
    response = client.post("/api/load", files={"file": ("shot.png", png_bytes, "image/png")})
    body = response.json()
    assert response.status_code == 200
    assert body["format"] == "png"
    assert body["targets"] == ["jpg", "pdf"]
    assert body["multi_targets"] == ["pdf"]
    assert body["pages"] == []


def test_load_pdf_returns_page_previews(client, pdf_bytes):
    response = client.post("/api/load", files={"file": ("doc.pdf", pdf_bytes, "application/pdf")})
    body = response.json()
    assert body["format"] == "pdf"
    assert len(body["pages"]) == 3
    assert body["pages"][0]["image"].startswith("data:image/png;base64,")


def test_load_rejects_unsupported_input(client):
    response = client.post("/api/load", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 400
    assert "supported" in response.json()["error"]


def test_load_ignores_a_lying_filename(client, png_bytes):
    """Detection uses magic bytes, so a PNG named .pdf is still a PNG."""
    response = client.post("/api/load", files={"file": ("shot.pdf", png_bytes, "application/pdf")})
    assert response.json()["format"] == "png"


def test_convert(client, jpg_bytes):
    response = client.post(
        "/api/convert",
        files={"file": ("photo.jpg", jpg_bytes, "image/jpeg")},
        data={"target": "pdf"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="photo.pdf"'
    assert loader.detect_format(response.content) == "pdf"


def test_convert_rejects_unavailable_target(client, pdf_bytes):
    response = client.post(
        "/api/convert",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        data={"target": "png"},
    )
    assert response.status_code == 400


def test_convert_combines_several_images_into_one_pdf(client, png_bytes):
    response = client.post(
        "/api/convert",
        files=[
            ("file", ("one.png", png_bytes, "image/png")),
            ("file", ("two.png", png_bytes, "image/png")),
        ],
        data={"target": "pdf"},
    )
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="one.pdf"'
    assert pdf.page_count(response.content) == 2


def test_convert_rejects_mixed_formats(client, png_bytes, jpg_bytes):
    response = client.post(
        "/api/convert",
        files=[
            ("file", ("one.png", png_bytes, "image/png")),
            ("file", ("two.jpg", jpg_bytes, "image/jpeg")),
        ],
        data={"target": "pdf"},
    )
    assert response.status_code == 400
    assert "same format" in response.json()["error"]


def test_crop(client, png_bytes):
    response = client.post(
        "/api/image/crop",
        files={"file": ("shot.png", png_bytes, "image/png")},
        data={"left": 0.0, "top": 0.5, "right": 0.5, "bottom": 1.0},
    )
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="shot.png"'
    assert loader.detect_format(response.content) == "png"


def test_crop_rejects_a_pdf(client, pdf_bytes):
    response = client.post(
        "/api/image/crop",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        data={"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0},
    )
    assert response.status_code == 400
    assert "cropped" in response.json()["error"]


def test_crop_reports_an_empty_selection(client, jpg_bytes):
    response = client.post(
        "/api/image/crop",
        files={"file": ("photo.jpg", jpg_bytes, "image/jpeg")},
        data={"left": 0.4, "top": 0.0, "right": 0.4, "bottom": 1.0},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["error"]


def test_compose_removes_and_reorders(client, pdf_bytes):
    response = client.post(
        "/api/pdf/compose",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        data={"pages": ["0:2", "0:0"]},
    )
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="doc.pdf"'
    assert pdf.page_count(response.content) == 2


def test_compose_merges_two_documents(client, pdf_bytes):
    response = client.post(
        "/api/pdf/compose",
        files=[
            ("file", ("a.pdf", pdf_bytes, "application/pdf")),
            ("file", ("b.pdf", pdf_bytes, "application/pdf")),
        ],
        data={"pages": ["0:0", "0:1", "0:2", "1:0", "1:1", "1:2"]},
    )
    assert response.status_code == 200
    assert pdf.page_count(response.content) == 6


def test_compose_reports_invalid_page(client, pdf_bytes):
    response = client.post(
        "/api/pdf/compose",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        data={"pages": ["0:9"]},
    )
    assert response.status_code == 400
    assert "does not exist" in response.json()["error"]


def test_compose_reports_a_malformed_reference(client, pdf_bytes):
    response = client.post(
        "/api/pdf/compose",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        data={"pages": ["first"]},
    )
    assert response.status_code == 400
    assert "reference" in response.json()["error"]


def test_compose_rejects_a_non_pdf(client, png_bytes):
    response = client.post(
        "/api/pdf/compose",
        files={"file": ("shot.png", png_bytes, "image/png")},
        data={"pages": ["0:0"]},
    )
    assert response.status_code == 400


def test_frontend_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "File Tool" in response.text
