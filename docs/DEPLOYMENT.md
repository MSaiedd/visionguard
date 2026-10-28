# Deployment and recovery

## Local

Run one Uvicorn app on 127.0.0.1:8003. Local auth permits loopback clients only and rejects public hostnames.
The model artifact is self-contained; inference needs no hub download or external API. Restart the service when
replacing it so the loaded model and evaluation agree. Keep artifacts read-only in serving deployments.

## Containers and PostgreSQL

Download the release before starting Compose, then set a random VISION_POSTGRES_PASSWORD in the ignored .env.
Compose publishes only the loopback app port; PostgreSQL stays on the private network. The image builds React,
installs ONNX Runtime CPU, runs as a non-root user and uses persistent metadata/source volumes.
Local Docker mode explicitly trusts the bridge range because the host port is loopback-bound. Never expose
that mode through a public proxy. No public default service credentials are provided.

For a public service, configure VISION_AUTH_MODE=oidc, issuer, audience, HTTPS JWKS URL and your hostname.
Tokens must include exp, iat, sub and workspace_id. roles is a list containing admin/editor/viewer. The browser
holds supplied access tokens only in memory. Full organization login/PKCE, account lifecycle and MFA remain
identity-provider integration work. TLS/proxy operation has not been validated by local checks.

Preserve Host and original scheme headers at your proxy. Trust forwarded headers only from specific proxy
addresses through Uvicorn FORWARDED_ALLOW_IPS, and restrict direct backend access. Match proxy/body limits to
10 MB images plus multipart overhead, and configure rate limits, storage quotas and request timeouts.

## Operations

SQLite is suitable for the local app; PostgreSQL is the multi-replica metadata path. The lease and attempt fence
allow independently started application workers without duplicate completion. The bundled implementation loads
one model per process; it is not a tuned fleet scheduler or GPU inference server. Benchmark actual concurrency,
queue waiting time, p95/p99 request completion and memory before sizing a deployment.

Back up metadata, source PNGs, overlays and the exact model artifact/digest together. Practice restore in an
isolated workspace and verify inspection visibility, model identity, pending leases, review revisions, audit,
media reads, exports and deletion. These code checks do not establish a restored live backup. Historical model
artifacts must remain available if old inspections need to be reproduced. Configure retention and orphan-file
cleanup appropriate to your deployment; a process crash between a file write and SQL commit can leave an
unreferenced private file.

The bundled dataset/model license is noncommercial. A commercial deployment needs rights for its data and
backbone, new representative reference images and target-domain evaluation. This app has been tested locally;
no factory integration, live OIDC provider, public hosting, GPU execution or traffic SLA is claimed.
