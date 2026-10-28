"""CI-only server with a deterministic neural substitute, never the product entry point."""

from tests.conftest import FixtureInspector
from visionguard.api import create_app
from visionguard.config import Settings
from visionguard.service import Runtime

app = create_app(
    Settings(model_loading=False, worker_enabled=True),
    runtime_factory=lambda settings, db: Runtime(settings, db, FixtureInspector()),
)
