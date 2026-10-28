"""Workspace-scoped visual inspection API and same-origin React frontend."""

import csv
import io
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import Authentication
from .config import Settings
from .middleware import BodyBudget
from .service import Runtime, get_row, path_for, row_dict, upload
from .store import Audit, Database, Inspection


class ReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["accepted", "rejected", "needs_attention", "pending"]
    note: str = Field(default="", max_length=2000)
    revision: int = Field(ge=0)


def create_app(settings=None, runtime_factory=Runtime, identity_override=None):
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite:///"):
        Path(settings.database_url[10:]).parent.mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_url)
    runtime = runtime_factory(settings, db)
    auth = identity_override or Authentication(settings)

    @asynccontextmanager
    async def lifespan(app):
        runtime.start()
        yield
        runtime.close()
        db.engine.dispose()

    app = FastAPI(title="VisionGuard", version="0.1.0", lifespan=lifespan)
    app.state.db = db
    app.state.runtime = runtime
    app.add_middleware(BodyBudget, settings=settings)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts.split(","))

    @app.middleware("http")
    async def browser_boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            parsed = urlsplit(origin)
            if parsed.netloc != request.url.netloc or parsed.scheme != request.url.scheme:
                return Response("Cross-origin writes are not allowed", 403)
        response = await call_next(request)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
            }
        )
        return response

    @app.get("/health")
    def health():
        return {
            "status": "ready" if runtime.ready else "loading",
            "models_ready": runtime.ready,
            "error": runtime.error,
            "version": "0.1.0",
        }

    @app.get("/ready", include_in_schema=False)
    def ready():
        if not runtime.ready:
            raise HTTPException(503, runtime.error or "Model is loading")
        return {"ready": True}

    @app.get("/api/workspace")
    def workspace(identity=Depends(auth)):
        with db.session() as session:
            rows = list(
                session.scalars(
                    select(Inspection).where(
                        Inspection.tenant == identity.tenant, Inspection.state != "deleted"
                    )
                )
            )
            complete = [r for r in rows if r.state == "complete"]
            return {
                "name": "Northline quality lab"
                if settings.auth_mode == "local"
                else identity.tenant,
                "identity": {
                    "user": identity.user,
                    "role": identity.role,
                    "auth_mode": settings.auth_mode,
                },
                "model": {
                    "ready": runtime.ready,
                    "error": runtime.error,
                    "metadata": runtime.inspector.metadata if runtime.ready else None,
                },
                "stats": {
                    "images": len(rows),
                    "complete": len(complete),
                    "queued": sum(r.state in {"queued", "running"} for r in rows),
                    "suspect": sum(r.decision in {"suspect", "review"} for r in complete),
                    "reviewed": sum(r.review != "pending" for r in complete),
                    "pending_review": sum(r.review == "pending" for r in complete),
                    "mean_latency_ms": round(sum(r.latency_ms for r in complete) / len(complete), 1)
                    if complete
                    else None,
                },
                "batches": sorted({r.batch for r in rows}),
            }

    @app.get("/api/inspections")
    def inspections(
        state: str | None = None,
        decision: str | None = None,
        review: str | None = None,
        batch: str | None = None,
        search: str = "",
        offset: int = 0,
        limit: int = 50,
        identity=Depends(auth),
    ):
        if not 1 <= limit <= 100 or offset < 0:
            raise HTTPException(422, "Invalid pagination")
        query = select(Inspection).where(
            Inspection.tenant == identity.tenant, Inspection.state != "deleted"
        )
        for field, value in [
            ("state", state),
            ("decision", decision),
            ("review", review),
            ("batch", batch),
        ]:
            if value:
                query = query.where(getattr(Inspection, field) == value)
        if search:
            query = query.where(Inspection.filename.ilike("%" + search[:120] + "%"))
        with db.session() as session:
            count = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = list(
                session.scalars(
                    query.order_by(Inspection.created_at.desc()).offset(offset).limit(limit)
                )
            )
            return {
                "items": [row_dict(r) for r in rows],
                "total": count,
                "offset": offset,
                "limit": limit,
            }

    @app.post("/api/inspections", status_code=202)
    async def add(
        request: Request,
        file: UploadFile = File(...),
        batch: str = Form("Manual upload"),
        identity=Depends(auth),
    ):
        identity.require_editor()
        if not batch.strip() or len(batch) > 120:
            raise HTTPException(422, "Batch name must have 1–120 characters")
        raw = await file.read(settings.max_upload_bytes + 1)
        return upload(db, settings, identity, file.filename or "image.png", raw, batch.strip())

    @app.get("/api/inspections/{identifier}")
    def detail(identifier: str, identity=Depends(auth)):
        with db.session() as session:
            return row_dict(get_row(session, identity, identifier))

    @app.get("/api/inspections/{identifier}/image")
    def image(identifier: str, kind: Literal["image", "heatmap"] = "image", identity=Depends(auth)):
        with db.session() as session:
            row = get_row(session, identity, identifier)
            if kind == "heatmap" and row.state != "complete":
                raise HTTPException(409, "Heatmap is not ready")
            path = path_for(settings, identity.tenant, identifier, kind)
            if not path.exists():
                raise HTTPException(404, "Image is unavailable")
            return FileResponse(path, media_type="image/png")

    @app.patch("/api/inspections/{identifier}/review")
    def review(identifier: str, body: ReviewBody, identity=Depends(auth)):
        identity.require_editor()
        with db.session() as session:
            row = get_row(session, identity, identifier)
            if row.state != "complete":
                raise HTTPException(409, "Wait for inspection to complete")
            previous = row.review
            changed = session.execute(
                update(Inspection)
                .where(
                    Inspection.id == identifier,
                    Inspection.tenant == identity.tenant,
                    Inspection.revision == body.revision,
                    Inspection.state == "complete",
                )
                .values(
                    review=body.decision,
                    review_note=body.note,
                    reviewed_by=identity.user,
                    revision=Inspection.revision + 1,
                    updated_at=time.time(),
                )
            )
            if not changed.rowcount:
                raise HTTPException(
                    409, "This review changed in another session; refresh before saving"
                )
            session.add(
                Audit(
                    tenant=identity.tenant,
                    user=identity.user,
                    action="review",
                    inspection_id=identifier,
                    detail={"before": previous, "after": body.decision, "note": body.note},
                )
            )
        with db.session() as session:
            return row_dict(get_row(session, identity, identifier))

    @app.post("/api/inspections/{identifier}/retry")
    def retry(identifier: str, identity=Depends(auth)):
        identity.require_editor()
        with db.session() as session:
            row = get_row(session, identity, identifier)
            if row.state != "failed":
                raise HTTPException(409, "Only failed inspections can be retried")
            row.state = "queued"
            row.attempts = 0
            row.error = ""
        return {"queued": True}

    @app.delete("/api/inspections/{identifier}")
    def delete(identifier: str, identity=Depends(auth)):
        identity.require_editor()
        with db.session() as session:
            row = get_row(session, identity, identifier)
            row.state = "deleted"
            row.updated_at = time.time()
            session.add(
                Audit(
                    tenant=identity.tenant,
                    user=identity.user,
                    action="delete",
                    inspection_id=identifier,
                )
            )
        for kind in ["image", "heatmap"]:
            path_for(settings, identity.tenant, identifier, kind).unlink(missing_ok=True)
        return {"deleted": True}

    @app.get("/api/evaluation")
    def evaluation(identity=Depends(auth)):
        path = settings.model_dir / "evaluation.json"
        if not path.exists():
            return {"available": False}
        report = json.loads(path.read_text())
        # Keep the browser payload useful; full split IDs remain in the downloaded report.
        return {
            "available": True,
            **{
                k: v
                for k, v in report.items()
                if k not in {"normal_training_ids", "validation_ids", "test_predictions"}
            },
        }

    @app.get("/api/export")
    def export(format: Literal["json", "csv"] = "csv", identity=Depends(auth)):
        with db.session() as session:
            rows = [
                row_dict(r)
                for r in session.scalars(
                    select(Inspection)
                    .where(Inspection.tenant == identity.tenant, Inspection.state == "complete")
                    .order_by(Inspection.created_at.desc())
                )
            ]
        if format == "json":
            return Response(
                json.dumps(rows, ensure_ascii=False),
                media_type="application/json",
                headers={
                    "Content-Disposition": 'attachment; filename="visionguard-inspections.json"'
                },
            )
        fields = [
            "id",
            "filename",
            "batch",
            "decision",
            "score",
            "threshold",
            "model_version",
            "review",
            "review_note",
            "reviewed_by",
            "latency_ms",
        ]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            # Neutralize spreadsheet formula interpretation in user-controlled text.
            writer.writerow(
                {
                    k: (
                        "'" + str(row[k])
                        if isinstance(row[k], str)
                        and row[k].startswith(("=", "+", "-", "@", "\t", "\r"))
                        else row[k]
                    )
                    for k in fields
                }
            )
        return Response(
            buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="visionguard-inspections.csv"'},
        )

    @app.get("/api/audit")
    def audit(identifier: str | None = None, identity=Depends(auth)):
        identity.require_editor()
        query = select(Audit).where(Audit.tenant == identity.tenant)
        if identifier:
            query = query.where(Audit.inspection_id == identifier)
        with db.session() as session:
            return [
                {
                    "id": r.id,
                    "action": r.action,
                    "inspection_id": r.inspection_id,
                    "user": r.user,
                    "detail": r.detail,
                    "created_at": r.created_at,
                }
                for r in session.scalars(query.order_by(Audit.created_at.desc()).limit(100))
            ]

    web = Path(__file__).parent / "web"
    if (web / "assets").exists():
        app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        if not (web / "index.html").exists():
            raise HTTPException(503, "Build the React frontend first")
        return FileResponse(web / "index.html")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        return FileResponse(web / "favicon.svg", media_type="image/svg+xml")

    return app
