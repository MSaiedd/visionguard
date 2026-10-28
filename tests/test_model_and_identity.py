import time
from types import SimpleNamespace

import jwt
import numpy as np
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request

from visionguard.auth import Authentication
from visionguard.config import Settings
from visionguard.model import patch_distances, regions_from_map
from visionguard.training import best_threshold, split_training


def test_real_mahalanobis_and_region_coordinates():
    torch = pytest.importorskip("torch")
    features = torch.tensor([[[3.0, 0.0], [4.0, 2.0]]])
    mean = torch.zeros((2, 2))
    precision = torch.eye(2)[None].repeat(2, 1, 1)
    torch.testing.assert_close(
        patch_distances(features, mean, precision), torch.tensor([[5.0, 2.0]])
    )
    values = np.zeros((20, 10))
    values[5:10, 2:6] = 8
    regions = regions_from_map(values, 5, (100, 200))
    assert len(regions) == 1
    assert {k: regions[0][k] for k in ["x", "y", "width", "height"]} == {
        "x": 20,
        "y": 50,
        "width": 40,
        "height": 50,
    }


def test_validation_split_and_threshold_selection():
    rows = [{"id": str(i), "label": int(i >= 20)} for i in range(30)]
    train, validation = split_training(rows)
    assert {r["id"] for r in train}.isdisjoint({r["id"] for r in validation})
    assert len(train) == 24 and len(validation) == 6
    assert best_threshold([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 0.8


def test_jwt_and_local_identity_validation():
    auth = Authentication(Settings())
    with pytest.raises(HTTPException):
        auth(Request({"type": "http", "headers": [], "client": ("198.51.100.9", 123)}))
    settings = Settings(
        auth_mode="oidc",
        oidc_issuer="https://issuer.example",
        oidc_audience="visionguard",
        oidc_jwks_url="https://issuer.example/keys",
    )
    auth = Authentication(settings)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    auth.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
    )
    values = {
        "iss": settings.oidc_issuer,
        "aud": settings.oidc_audience,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "sub": "bob",
        "workspace_id": "beta",
        "roles": ["editor"],
    }

    def call(claims):
        token = jwt.encode(claims, private, algorithm="RS256")
        return auth(
            Request({"type": "http", "headers": [(b"authorization", ("Bearer " + token).encode())]})
        )

    assert call(values).tenant == "beta"
    for change in [{"exp": 1}, {"aud": "other"}, {"roles": "admin"}, {"workspace_id": ""}]:
        with pytest.raises(HTTPException):
            call({**values, **change})


def test_numpy_serving_map_matches_training_math():
    torch = pytest.importorskip("torch")
    from visionguard.model import numpy_maps, smooth_maps

    features = np.arange(32, dtype=np.float32).reshape(1, 2, 4, 4) / 10
    mean = np.zeros((2, 16), dtype=np.float32)
    precision = np.repeat(np.eye(2, dtype=np.float32)[None], 16, axis=0)
    distances = patch_distances(
        torch.from_numpy(features).flatten(2), torch.from_numpy(mean), torch.from_numpy(precision)
    )
    expected = smooth_maps(distances, (4, 4), 16, 16)
    actual = numpy_maps(features, mean, precision, 16, 16)
    np.testing.assert_allclose(actual, expected, atol=1e-5)
