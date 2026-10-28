"""CI-only neural substitute. HTTP, image decoding, SQL, leases and reviews remain real."""

import io
import os

import numpy as np
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete

from visionguard.api import create_app
from visionguard.auth import Identity
from visionguard.config import Settings
from visionguard.model import regions_from_map
from visionguard.service import Runtime
from visionguard.store import Base


class FixtureInspector:
    version = "fixture-only"
    metadata = {
        "version": version,
        "heatmap_low": 0,
        "heatmap_high": 10,
        "image_threshold": 5,
        "pixel_threshold": 5,
        "backbone": "CI substitute",
        "method": "CI substitute",
        "input_size": [32, 32],
        "dimensions": 1,
        "fitted_normal_images": 0,
        "score_definition": "CI substitute",
        "weights_sha256": "fixture",
        "dataset": "Generated test images",
        "license": "original test fixture",
    }

    def predict(self, image):
        values = np.zeros((32, 32), dtype=np.float32)
        values[10:20, 12:19] = 9
        return {
            "score": 9.0,
            "threshold": 5.0,
            "decision": "suspect",
            "regions": regions_from_map(values, 5, image.size),
            "latency_ms": 1.0,
            "model_version": self.version,
            "map": values,
        }


def test_identity(request: Request):
    return Identity(
        request.headers.get("x-test-tenant", "alpha"),
        request.headers.get("x-test-user", "alice"),
        request.headers.get("x-test-role", "admin"),
    )


test_identity.__test__ = False


@pytest.fixture
def harness(tmp_path):
    url = os.environ.get("VISION_TEST_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    if not url.startswith("sqlite") and not url.endswith("/visionguard_test"):
        pytest.fail("Use a disposable PostgreSQL database named visionguard_test")
    settings = Settings(
        _env_file=None,
        auth_mode="local",
        allowed_hosts="testserver,localhost,127.0.0.1",
        database_url=url,
        data_dir=tmp_path / "images",
        model_dir=tmp_path / "model",
        model_loading=False,
        worker_enabled=False,
    )

    def factory(settings, db):
        if not url.startswith("sqlite"):
            with db.session() as session:
                for table in reversed(Base.metadata.sorted_tables):
                    session.execute(delete(table))
        return Runtime(settings, db, FixtureInspector())

    app = create_app(settings, factory, test_identity)
    with TestClient(app) as client:
        yield client, app.state.db, app.state.runtime, settings


@pytest.fixture
def image_bytes():
    def make(color="gray", size=(96, 128)):
        buffer = io.BytesIO()
        Image.new("RGB", size, color).save(buffer, format="PNG")
        return buffer.getvalue()

    return make


def add_image(client, raw, **kwargs):
    return client.post(
        "/api/inspections",
        files={"file": (kwargs.pop("filename", "surface.png"), raw, "image/png")},
        data={"batch": kwargs.pop("batch", "Fixture batch")},
        **kwargs,
    )
