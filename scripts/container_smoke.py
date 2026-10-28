"""Validate actual-model container inference, non-root execution and restart persistence."""

import argparse
import io
import json
import socket
import subprocess
import time
import uuid
from pathlib import Path

import httpx
from PIL import Image


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def wait_ready(client):
    for _ in range(100):
        try:
            if client.get("/ready").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    raise RuntimeError("Container model did not become ready")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="visionguard:local")
    args = parser.parse_args()
    name = "visionguard-model-check-" + uuid.uuid4().hex[:8]
    volume = name + "-data"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    docker("volume", "create", volume)
    try:
        docker(
            "run",
            "-d",
            "--name",
            name,
            "-p",
            f"127.0.0.1:{port}:8000",
            "-e",
            "VISION_LOCAL_CLIENT_NETWORKS=127.0.0.0/8,172.16.0.0/12",
            "-v",
            volume + ":/app/data",
            "-v",
            str(Path("artifacts").resolve()) + ":/app/artifacts:ro",
            args.image,
        )
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=15) as client:
            wait_ready(client)
            assert client.get("/").status_code == 200
            uid = int(docker("exec", name, "id", "-u"))
            assert uid != 0
            sample = Path("data/samples/20099.png")
            response = client.post(
                "/api/inspections",
                data={"batch": "Container verification"},
                files={"file": (sample.name, sample.read_bytes(), "image/png")},
            )
            response.raise_for_status()
            identifier = response.json()["id"]
            for _ in range(100):
                row = client.get("/api/inspections/" + identifier).json()
                if row["state"] == "complete":
                    break
                if row["state"] == "failed":
                    raise RuntimeError(row["error"])
                time.sleep(0.2)
            assert row["state"] == "complete" and row["model_version"].startswith("surface-v1-")
            assert row["score"] is not None
            media = client.get("/api/inspections/" + identifier + "/image?kind=heatmap")
            media.raise_for_status()
            with Image.open(io.BytesIO(media.content)) as decoded:
                assert decoded.width == row["width"]
            review = client.patch(
                "/api/inspections/" + identifier + "/review",
                json={
                    "decision": "needs_attention",
                    "revision": 0,
                    "note": "Automated container persistence check.",
                },
            )
            review.raise_for_status()
            docker("restart", name)
            wait_ready(client)
            persisted = client.get("/api/inspections/" + identifier).json()
            assert persisted["review"] == "needs_attention" and persisted["score"] == row["score"]
            assert client.delete("/api/inspections/" + identifier).status_code == 200
            assert client.get("/api/inspections/" + identifier + "/image").status_code == 404
            report = {
                "passed": True,
                "image_id": docker("image", "inspect", args.image, "--format", "{{.Id}}"),
                "uid": uid,
                "real_model_version": row["model_version"],
                "real_score": row["score"],
                "inference_ms": row["latency_ms"],
                "checks": [
                    "built frontend",
                    "actual CPU model inference",
                    "heatmap PNG",
                    "non-root user",
                    "review persisted across restart",
                    "deleted image inaccessible",
                ],
            }
            Path("reports/container.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2))
    except Exception:
        print(docker("logs", name))
        raise
    finally:
        subprocess.run(["docker", "rm", "-fv", name], check=False, stdout=subprocess.DEVNULL)
        subprocess.run(["docker", "volume", "rm", volume], check=False, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
