# Validation evidence

This project is locally validated. A public deployment, factory integration and commercial model rights are not claimed.

## Real model fitting and official test evaluation

`python scripts/download_data.py` — downloaded the original ViCoS archive and recorded SHA-256
edcdb486809b24f1d17b785e30c52fafc5999554dd5fe18ddf77b61ceb6f36a8.
The source contains a duplicate copy of image 10301 and its mask; byte equality is verified before exclusion.
Exact image duplicates in the remaining train/test images: zero.

`python -m visionguard.training --max-normal 1000 --dimensions 48 --batch-size 8` — fitted the
normal-reference distributions and evaluated all 1,004 official test images on CPU. The initial fit/evaluation
finished in 66.31 seconds, excluding the initial pretrained-weight download. The backbone was frozen;
Gaussian statistics were fitted, not gradient fine-tuned. Validation selected image/pixel thresholds separately.

Training partition: 1,865 images, of which 1,000 normal images were used for reference fitting. Validation:
466 images (49 defective). Official test: 1,004 images (110 defective). There is no physical-item grouping
metadata, so exact deduplication and image-level splits are not proof of complete related-item independence.

| Test metric | Result |
| --- | ---: |
| Image AUROC | 0.937960 |
| Image average precision | 0.812732 |
| Precision | 0.747748 |
| Recall | 0.754545 |
| F1 | 0.751131 |
| True negatives / false positives | 866 / 28 |
| False negatives / true positives | 27 / 83 |
| Sampled pixel AUROC | 0.972973 |

Pixel measurements use a fixed stride-4 sample of resized 320×128 masks. The raw report includes split IDs,
archive identity, model/statistic identity, configuration and every test image score. It is not a claim to
reproduce a published PaDiM benchmark. See reports/evaluation.json and MODEL_CARD.md.

## ONNX serving export

`export_serving('artifacts/surface-v1')` exported the already-fitted encoder and reference statistics.
`python scripts/validate_export.py` compared all 1,004 official test scores with the recorded PyTorch run.
Maximum absolute score difference: 0.000053923. The maximum map difference on four comparison images was
0.000007868. Both are below the declared 0.002 numerical tolerance. All binary decisions/confusion counts
matched. Tiny score rounding differences changed AUROC only in the fifth decimal place.

ONNX Runtime 1.31.1 CPU: mean single-image preprocessing + encoder + map time 15.69 ms, p95 16.13 ms.
This excludes image disk I/O and HTTP. The original batched PyTorch evaluation was 21.10 ms/image at batch
size 8; these are different workloads, not a controlled speedup benchmark. Reports/onnx-parity.json records
all deployment-check scopes. The serving image uses ONNX Runtime; PyTorch is required only for fitting/export.

## Backend regression and PostgreSQL

`pytest --cov=src --cov-report=term-missing -q` — 14 passed locally. Workspace fixtures substitute only the
neural model; HTTP, bounded image decoding, SQL, file storage, leases, review updates and audit queries are real.
The suite includes real Mahalanobis/map math, workspace isolation, roles, signed/expired/wrong-audience JWTs,
optimistic review conflicts, formula-safe CSV, duplicate ingestion, deletion, stale-worker fencing, retries,
request-size limits and chunked-body limits. The tiny numerical tests require torch and are skipped in a core-only install.

`VISION_TEST_DATABASE_URL=postgresql+psycopg://.../visionguard_test pytest tests/test_workspace.py -q` —
10 passed against PostgreSQL 17.11 in a disposable local container. The fixture refuses to clear a server
database unless its name is visionguard_test. Local developer .env settings are excluded from test configuration.

## Frontend and browser

- `npm run check --prefix frontend` — TypeScript passed.
- `npm run format:check --prefix frontend` — passed.
- `npm test --prefix frontend` — four transport tests passed: identity header, optimistic conflict, unavailable server and multipart upload.
- `npm audit --prefix frontend --audit-level=moderate` — zero reported vulnerabilities.
- `npm run build --prefix frontend` — passed.
- `python scripts/browser_smoke.py` — passed with an explicitly isolated CI neural substitute.
- `python scripts/browser_smoke.py --url http://127.0.0.1:8003 --image data/ksdd2/test/20101.png --screenshots docs/screenshots` — passed with the actual ONNX model.

Both browser flows cover upload, queue completion, image/heatmap display, review persistence, audit visibility,
desktop navigation and phone layout. There were no uncaught browser errors or horizontal overflow in the
checked phone views. Browser test review notes explicitly identify workflow verification; they are not expert
inspection labels. Published screenshots show actual model output and measured report data, not CI predictions.

## External validation boundaries

No live organizational identity provider, public TLS/proxy, account lifecycle, commercial dataset permission,
factory camera feed, domain shift, live backup restoration, stress capacity or GPU run has been established.
The code/configuration expose hosted identity and PostgreSQL paths, but operational rollout needs validation
in that target environment. The model missed 27 official test defects; it must not autonomously certify items.

## Actual container

`docker build -t visionguard:local .` — passed for the ONNX serving image.
`python scripts/container_smoke.py` — passed with the real fitted artifact: built frontend, CPU inference,
heatmap PNG, UID 1000, review persistence across container restart, and deletion visibility. The recorded
model was surface-v1-bf19df23, sample anomaly score 7.7677. Reports/container.json identifies the image.
This does not establish public deployment, load capacity or live recovery.
