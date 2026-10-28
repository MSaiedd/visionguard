"""Bounded image intake, durable leases and real-model execution."""

import hashlib
import io
import logging
import threading
import time
import uuid
import warnings
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from .model import Inspector, render_heatmap
from .store import Audit, Inspection

logger = logging.getLogger(__name__)


def path_for(settings, tenant, identifier, kind="image"):
    workspace = hashlib.sha256(tenant.encode()).hexdigest()[:32]
    return settings.data_dir / workspace / f"{identifier}-{kind}.png"


def row_dict(row):
    fields = [
        "id",
        "filename",
        "batch",
        "width",
        "height",
        "state",
        "attempts",
        "created_at",
        "updated_at",
        "score",
        "threshold",
        "decision",
        "regions",
        "latency_ms",
        "model_version",
        "error",
        "review",
        "review_note",
        "reviewed_by",
        "revision",
    ]
    return {field: getattr(row, field) for field in fields}


def get_row(session, identity, identifier):
    row = session.scalar(
        select(Inspection).where(
            Inspection.id == identifier,
            Inspection.tenant == identity.tenant,
            Inspection.state != "deleted",
        )
    )
    if row is None:
        raise HTTPException(404, "Inspection not found")
    return row


def decode_image(raw, settings):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if (
                    source.format not in {"PNG", "JPEG", "WEBP"}
                    or getattr(source, "n_frames", 1) != 1
                ):
                    raise ValueError("Upload a single PNG, JPEG or WebP image")
                if source.width * source.height > settings.max_pixels or min(source.size) < 32:
                    raise ValueError("Images must be at least 32×32 and at most 12 megapixels")
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.load()
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValueError("Invalid image or image exceeds the pixel budget") from error
    output = io.BytesIO()
    image.save(output, format="PNG")
    return image, output.getvalue()


def upload(db, settings, identity, filename, raw, batch):
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(413, "Image exceeds 10 MB upload limit")
    try:
        image, encoded = decode_image(raw, settings)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    digest = hashlib.sha256(encoded).hexdigest()
    with db.session() as session:
        existing = session.scalar(
            select(Inspection).where(
                Inspection.tenant == identity.tenant, Inspection.content_hash == digest
            )
        )
        if existing and existing.state != "deleted":
            return {**row_dict(existing), "duplicate": True}
        if (
            session.scalar(
                select(func.count())
                .select_from(Inspection)
                .where(
                    Inspection.tenant == identity.tenant,
                    Inspection.state.in_(["queued", "running"]),
                )
            )
            >= settings.max_queued
        ):
            raise HTTPException(
                429,
                "Workspace indexing queue is full; try again after current inspections complete",
            )
        if existing:
            # A deleted hash may be uploaded again; retain the historic audit trail.
            existing.content_hash = "deleted-" + existing.id
        row = Inspection(
            id=str(uuid.uuid4()),
            tenant=identity.tenant,
            filename=Path(filename.replace("\\", "/")).name[:240] or "image.png",
            batch=batch,
            width=image.width,
            height=image.height,
            content_hash=digest,
        )
        session.add(row)
        path = path_for(settings, identity.tenant, row.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            session.flush()
            path.write_bytes(encoded)
            path.chmod(0o600)
            session.add(
                Audit(
                    tenant=identity.tenant,
                    user=identity.user,
                    action="upload",
                    inspection_id=row.id,
                    detail={"batch": batch},
                )
            )
            session.commit()
        except IntegrityError:
            path.unlink(missing_ok=True)
            session.rollback()
            duplicate = session.scalar(
                select(Inspection).where(
                    Inspection.tenant == identity.tenant, Inspection.content_hash == digest
                )
            )
            if duplicate:
                return {**row_dict(duplicate), "duplicate": True}
            raise
        return {**row_dict(row), "duplicate": False}


class Runtime:
    def __init__(self, settings, db, inspector=None):
        self.settings, self.db, self.inspector = settings, db, inspector
        self.ready = inspector is not None
        self.error = ""
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        if self.settings.worker_enabled or self.settings.model_loading:
            self.thread = threading.Thread(
                target=self.run, daemon=True, name="visionguard-inspector"
            )
            self.thread.start()

    def run(self):
        if not self.ready and self.settings.model_loading:
            try:
                self.inspector = Inspector(self.settings.model_dir)
                self.ready = True
            except Exception:
                logger.exception("Vision model failed to initialize")
                self.error = "Model unavailable. Install a verified surface-v1 artifact and restart the service."
        while not self.stop.wait(0.4):
            if self.ready and self.settings.worker_enabled:
                try:
                    self.process_one()
                except Exception:
                    logger.exception("Inspection worker failed")

    def process_one(self):
        now = time.time()
        with self.db.session() as session:
            session.execute(
                update(Inspection)
                .where(
                    Inspection.state == "running",
                    Inspection.lease_until < now,
                    Inspection.attempts < 3,
                )
                .values(state="queued")
            )
            session.execute(
                update(Inspection)
                .where(
                    Inspection.state == "running",
                    Inspection.lease_until < now,
                    Inspection.attempts >= 3,
                )
                .values(state="failed", error="Worker lease expired after three attempts")
            )
            row = session.scalar(
                select(Inspection)
                .where(Inspection.state == "queued")
                .order_by(Inspection.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return False
            attempt = row.attempts + 1
            changed = session.execute(
                update(Inspection)
                .where(Inspection.id == row.id, Inspection.state == "queued")
                .values(state="running", attempts=Inspection.attempts + 1, lease_until=now + 300)
            )
            if not changed.rowcount:
                return False
            identifier, tenant = row.id, row.tenant
        try:
            with Image.open(path_for(self.settings, tenant, identifier)) as source:
                image = source.convert("RGB")
            result = self.inspector.predict(image)
            values = result.pop("map")
            metadata = self.inspector.metadata
            overlay = render_heatmap(
                image, values, metadata["heatmap_low"], metadata["heatmap_high"]
            )
            destination = path_for(self.settings, tenant, identifier, "heatmap")
            temporary = destination.with_suffix("." + uuid.uuid4().hex + ".tmp")
            overlay.save(temporary, format="PNG")
            temporary.chmod(0o600)
            with self.db.session() as session:
                # The conditional update fences stale workers and holds the row write lock
                # until its matching overlay is installed. A deletion always wins visibility.
                changed = session.execute(
                    update(Inspection)
                    .where(
                        Inspection.id == identifier,
                        Inspection.state == "running",
                        Inspection.attempts == attempt,
                    )
                    .values(**result, state="complete", updated_at=time.time(), error="")
                )
                if not changed.rowcount:
                    temporary.unlink(missing_ok=True)
                    return True
                temporary.replace(destination)
        except Exception:
            logger.exception("Inspection failed: %s", identifier)
            with self.db.session() as session:
                session.execute(
                    update(Inspection)
                    .where(
                        Inspection.id == identifier,
                        Inspection.state == "running",
                        Inspection.attempts == attempt,
                    )
                    .values(
                        state="failed",
                        error="Inspection failed. Retry or check server logs.",
                        updated_at=time.time(),
                    )
                )
        finally:
            if "temporary" in locals():
                temporary.unlink(missing_ok=True)
        return True

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=10)
