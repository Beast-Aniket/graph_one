from graphone.main import app


def test_openapi_contains_required_backend_surfaces() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/sources" in paths
    assert "/api/v1/crawl-jobs" in paths
    assert "/api/v1/records" in paths
    assert "/api/v1/github/refresh" in paths
    assert "/api/v1/exports/{tab}.csv" in paths

