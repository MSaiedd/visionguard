# Contributing

Use Python 3.11/3.12 and Node 22.12+. Install .[dev] for core checks, .[vision] for model fitting/inference.
Run ruff check ., ruff format --check ., pytest, npm run check --prefix frontend, npm test --prefix frontend,
npm audit --prefix frontend --audit-level=moderate, and npm run build --prefix frontend.

playwright install chromium then python scripts/browser_smoke.py runs an isolated CI neural substitute.
For actual inference/browser checks, first load a verified model and use --url with --image. Do not describe
substitute checks as model accuracy measurements. Keep model fitting/threshold selection separate from test
measurement. Record data/model provenance and update docs whenever behavior or operational requirements change.

Do not commit .env, runtime databases, uploaded images, dataset archives, model weights or node_modules.
Use attributed release assets for reference material. Application code is MIT; dataset-derived material retains
its upstream noncommercial/share-alike terms. Keep optional suggestions separate from correctness/security fixes.
