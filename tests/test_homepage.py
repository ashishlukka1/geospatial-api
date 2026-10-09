"""Tests for Iteration 3.5 viewer page. Uses shared test DB from conftest."""

from pathlib import Path

MIXED_KML = Path("sample_data/mixed.kml").read_bytes()


def test_home_returns_html_page(client):
    """GET / returns the Leaflet viewer page, not JSON."""
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "leaflet" in res.text.lower()
    assert "/static/app.js" in res.text
    js = client.get("/static/app.js").text
    assert "/api/files/" in js


def test_static_js_served(client):
    """Viewer JS is served from /static."""
    res = client.get("/static/app.js")
    assert res.status_code == 200
    assert "fetch" in res.text


def test_static_css_served(client):
    """Viewer CSS is served from /static."""
    res = client.get("/static/app.css") if False else client.get("/static/style.css")
    assert res.status_code == 200
    assert "#map" in res.text


def test_health_still_json(client):
    """Existing /health endpoint is unchanged."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "healthy"}


def test_measurements_still_include_geometry(client):
    """Viewer depends on stored GeoJSON; ensure no regression."""
    up = client.post("/api/files/", files={"file": ("mixed.kml", MIXED_KML)})
    assert up.status_code == 200
    file_id = up.json()["id"]
    body = client.get(f"/api/files/{file_id}/measurements/").json()
    assert len(body["features"]) == 3
    assert all(f["geometry"] and f["geometry"]["type"] for f in body["features"])
