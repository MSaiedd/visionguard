"""Queue twelve attributed benchmark examples; predictions still run through the real model."""

from pathlib import Path

from .auth import Identity
from .config import Settings
from .service import upload
from .store import Database
from .training import records


def main():
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite:///"):
        Path(settings.database_url[10:]).parent.mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_url)
    identity = Identity(settings.local_tenant, "example-loader", "admin")
    samples = Path("data/samples")
    if samples.exists():
        paths = sorted(samples.glob("*.png"))
    else:
        rows = records("data/ksdd2", "test")
        paths = [
            Path(r["image"])
            for label in [1, 0]
            for r in [r for r in rows if r["label"] == label][:6]
        ]
    for path in paths:
        result = upload(
            db, settings, identity, "ksdd2-" + path.name, path.read_bytes(), "Reference collection"
        )
        print(f"{result['filename']}: {'already present' if result['duplicate'] else 'queued'}")
    db.engine.dispose()


if __name__ == "__main__":
    main()
