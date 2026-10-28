import io
import time

from PIL import Image
from sqlalchemy import select

from visionguard.service import path_for
from visionguard.store import Inspection

from .conftest import add_image


def test_upload_real_processing_heatmap_and_duplicate(harness, image_bytes):
    client, db, runtime, settings = harness
    response = add_image(client, image_bytes())
    assert response.status_code == 202
    row = response.json()
    assert row["state"] == "queued"
    assert add_image(client, image_bytes()).json()["id"] == row["id"]
    assert runtime.process_one()
    completed = client.get("/api/inspections/" + row["id"]).json()
    assert completed["state"] == "complete" and completed["regions"]
    media = client.get("/api/inspections/" + row["id"] + "/image?kind=heatmap")
    assert media.status_code == 200 and media.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(media.content)) as im:
        assert im.size == (96, 128)
    assert client.get("/ready").status_code == 200
    assert client.get("/api/workspace").json()["stats"]["complete"] == 1
    assert path_for(settings, "alpha", row["id"]).stat().st_mode & 0o777 == 0o600


def test_workspace_isolation_and_viewer_permissions(harness, image_bytes):
    client, _, runtime, _ = harness
    identifier = add_image(client, image_bytes()).json()["id"]
    runtime.process_one()
    foreign = {"x-test-tenant": "beta"}
    assert client.get("/api/inspections", headers=foreign).json()["total"] == 0
    for path in ["", "/image", "/image?kind=heatmap"]:
        assert (
            client.get("/api/inspections/" + identifier + path, headers=foreign).status_code == 404
        )
    assert client.delete("/api/inspections/" + identifier, headers=foreign).status_code == 404
    viewer = {"x-test-role": "viewer"}
    assert add_image(client, image_bytes("red"), headers=viewer).status_code == 403
    assert (
        client.patch(
            "/api/inspections/" + identifier + "/review",
            headers=viewer,
            json={"decision": "accepted", "revision": 0},
        ).status_code
        == 403
    )
    assert client.get("/api/audit", headers=viewer).status_code == 403
    assert client.get("/api/audit", headers=foreign).json() == []
    assert add_image(client, image_bytes(), headers=foreign).json()["id"] != identifier


def test_review_history_and_optimistic_conflict(harness, image_bytes):
    client, _, runtime, _ = harness
    identifier = add_image(client, image_bytes()).json()["id"]
    path = "/api/inspections/" + identifier + "/review"
    assert client.patch(path, json={"decision": "accepted", "revision": 0}).status_code == 409
    runtime.process_one()
    first = client.patch(
        path, json={"decision": "rejected", "revision": 0, "note": "Visible surface defect"}
    )
    assert first.status_code == 200 and first.json()["revision"] == 1
    assert client.patch(path, json={"decision": "accepted", "revision": 0}).status_code == 409
    assert (
        client.patch(
            path, json={"decision": "accepted", "revision": 1, "tenant": "beta"}
        ).status_code
        == 422
    )
    second = client.patch(
        path, json={"decision": "needs_attention", "revision": 1, "note": "Second review requested"}
    )
    assert second.json()["revision"] == 2
    audits = client.get("/api/audit?identifier=" + identifier).json()
    assert [r["detail"]["after"] for r in audits if r["action"] == "review"] == [
        "needs_attention",
        "rejected",
    ]


def test_image_validation_body_limit_and_queue_budget(harness, image_bytes):
    client, _, _, settings = harness
    assert add_image(client, b"<svg>bad</svg>").status_code == 422
    assert add_image(client, image_bytes(size=(20, 20))).status_code == 422
    settings.max_pixels = 1000
    assert add_image(client, image_bytes()).status_code == 422
    settings.max_pixels = 12000000
    settings.max_upload_bytes = 100
    assert add_image(client, image_bytes()).status_code == 413
    assert (
        client.post(
            "/api/inspections", content=b"a", headers={"content-length": "10000000"}
        ).status_code
        == 413
    )
    settings.max_upload_bytes = 1000000
    settings.max_queued = 1
    assert add_image(client, image_bytes()).status_code == 202
    assert add_image(client, image_bytes("red")).status_code == 429
    assert add_image(client, image_bytes(), batch=" ").status_code == 422


def test_delete_tombstone_removes_media_and_reupload(harness, image_bytes):
    client, _, runtime, settings = harness
    identifier = add_image(client, image_bytes()).json()["id"]
    runtime.process_one()
    assert client.delete("/api/inspections/" + identifier).status_code == 200
    assert client.get("/api/inspections/" + identifier).status_code == 404
    assert not path_for(settings, "alpha", identifier).exists()
    assert not path_for(settings, "alpha", identifier, "heatmap").exists()
    assert client.get("/api/inspections").json()["total"] == 0
    assert add_image(client, image_bytes()).json()["id"] != identifier
    assert any(r["action"] == "delete" for r in client.get("/api/audit").json())


def test_worker_recovery_failure_and_retry(harness, image_bytes):
    client, db, runtime, settings = harness
    identifier = add_image(client, image_bytes()).json()["id"]
    with db.session() as session:
        row = session.get(Inspection, identifier)
        row.state = "running"
        row.lease_until = time.time() - 1
        row.attempts = 1
    runtime.process_one()
    assert client.get("/api/inspections/" + identifier).json()["state"] == "complete"
    other = add_image(client, image_bytes("blue")).json()["id"]
    path_for(settings, "alpha", other).unlink()
    runtime.process_one()
    assert client.get("/api/inspections/" + other).json()["state"] == "failed"
    assert client.post("/api/inspections/" + other + "/retry").status_code == 200
    assert client.post("/api/inspections/" + identifier + "/retry").status_code == 409


def test_export_filters_and_formula_neutralization(harness, image_bytes):
    client, db, runtime, _ = harness
    row = add_image(client, image_bytes(), filename="=SUM(1).png", batch="=command").json()
    runtime.process_one()
    client.patch(
        "/api/inspections/" + row["id"] + "/review",
        json={"decision": "accepted", "revision": 0, "note": "@badformula"},
    )
    exported = client.get("/api/export").text
    assert "'=command" in exported and "'@badformula" in exported and "'=SUM(1).png" in exported
    assert client.get("/api/inspections?review=accepted").json()["total"] == 1
    assert client.get("/api/inspections?decision=clear").json()["total"] == 0
    assert client.get("/api/inspections?batch=other").json()["total"] == 0
    assert client.get("/api/inspections?limit=10000").status_code == 422
    assert client.get("/api/export?format=json", headers={"x-test-tenant": "beta"}).json() == []
    with db.session() as session:
        assert session.scalar(select(Inspection)).review == "accepted"


def test_cross_origin_and_unready_visibility(harness, image_bytes):
    client, _, runtime, _ = harness
    assert (
        add_image(client, image_bytes(), headers={"origin": "https://evil.example"}).status_code
        == 403
    )
    runtime.ready = False
    assert client.get("/ready").status_code == 503
    assert client.get("/api/workspace").status_code == 200
    assert not client.get("/api/workspace").json()["model"]["ready"]


def test_stale_worker_cannot_revive_deleted_or_reclaimed_job(harness, image_bytes):
    client, db, runtime, settings = harness
    identifier = add_image(client, image_bytes()).json()["id"]
    original = runtime.inspector.predict

    def stale(image):
        result = original(image)
        with db.session() as session:
            row = session.get(Inspection, identifier)
            row.attempts += 1
            row.state = "running"
        return result

    runtime.inspector.predict = stale
    runtime.process_one()
    assert client.get("/api/inspections/" + identifier).json()["state"] == "running"
    assert not path_for(settings, "alpha", identifier, "heatmap").exists()
    with db.session() as session:
        session.get(Inspection, identifier).state = "queued"

    def deleted(image):
        result = original(image)
        with db.session() as session:
            session.get(Inspection, identifier).state = "deleted"
        return result

    runtime.inspector.predict = deleted
    runtime.process_one()
    assert client.get("/api/inspections/" + identifier).status_code == 404
    assert not path_for(settings, "alpha", identifier, "heatmap").exists()


def test_chunked_upload_cannot_bypass_request_budget(harness):
    client, _, _, settings = harness
    settings.max_upload_bytes = 100
    prefix = b'--guard\r\nContent-Disposition: form-data; name="file"; filename="a.png"\r\nContent-Type: image/png\r\n\r\n'
    chunks = iter([prefix, *([b"x" * 20000] * 8), b"\r\n--guard--\r\n"])
    response = client.post(
        "/api/inspections",
        content=chunks,
        headers={"content-type": "multipart/form-data; boundary=guard"},
    )
    assert response.status_code == 413
