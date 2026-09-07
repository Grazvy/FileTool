from backend.services import loader, pdf


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_load_image_offers_conversion_targets(client, png_bytes):
    response = client.post("/api/load", files={"file": ("shot.png", png_bytes, "image/png")})
    body = response.json()
    assert response.status_code == 200
    assert body["format"] == "png"
    assert body["targets"] == ["jpg", "pdf"]
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


def test_remove_pages(client, pdf_bytes):
    response = client.post(
        "/api/pdf/remove-pages",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        data={"pages": ["0", "2"]},
    )
    assert response.status_code == 200
    assert pdf.page_count(response.content) == 1


def test_remove_pages_reports_invalid_page(client, pdf_bytes):
    response = client.post(
        "/api/pdf/remove-pages",
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
        data={"pages": ["9"]},
    )
    assert response.status_code == 400
    assert "does not exist" in response.json()["error"]


def test_frontend_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "File Tool" in response.text
