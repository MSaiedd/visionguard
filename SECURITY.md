# Security boundaries

Local mode is explicitly loopback-only. Public servers must use OIDC, real hostnames and TLS. Signed JWT
issuer, audience, expiry and workspace claims are verified. Editor/admin may modify records; viewers can
read their workspace. A workspace is a shared inspection boundary, not per-user private storage.

File types are determined by image decoding. The app accepts only single-frame PNG/JPEG/WebP, bounds request
bytes and pixels, removes metadata and stores generated paths with restrictive file modes. Trusted serving
artifacts use SHA-256-verified ONNX graphs and NumPy archives loaded without pickle; do not point the server at an untrusted artifact directory.
Uploaded text is escaped by React; user-controlled CSV cells are neutralized against formula interpretation.
Write requests with a mismatched browser Origin are rejected. Security headers block framing and active content.

Review revisions prevent silent last-writer overwrite, audit entries preserve review decisions, and worker
completion fences protect deletion and reclaimed jobs. SQL access uses bound expressions. Human reviews do not
mutate the model or automatically approve future products.

Local validation covers these code paths; production rate limits, managed identity lifecycle, TLS, backups,
restore drills, storage quotas and monitoring require deployment-specific verification. An anomaly score is
not a safety certificate. Report reproducible defects privately to the repository owner; do not upload secrets
or third-party images without permission in public issues.
