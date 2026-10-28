"""Compare the deployed ONNX path with the recorded PyTorch scores on the full official test split."""

import importlib.metadata
import json
from pathlib import Path

import numpy as np
from PIL import Image

from visionguard.model import Inspector, TorchInspector
from visionguard.training import metrics


def main():
    report = json.loads(Path("reports/evaluation.json").read_text())
    root = Path("artifacts/surface-v1")
    onnx = Inspector(root)
    torch_model = TorchInspector(root)
    scores = []
    labels = []
    differences = []
    latencies = []
    map_differences = []
    for index, row in enumerate(report["test_predictions"]):
        with Image.open(Path("data/ksdd2") / row["id"]) as source:
            image = source.convert("RGB")
        actual = onnx.predict(image)
        scores.append(actual["score"])
        labels.append(row["label"])
        latencies.append(actual["latency_ms"])
        differences.append(abs(actual["score"] - row["score"]))
        if index < 4:
            reference = torch_model.predict(image)
            map_differences.append(float(np.abs(actual["map"] - reference["map"]).max()))
        if (index + 1) % 100 == 0:
            print(f"Validated {index + 1} / 1004 ONNX predictions", flush=True)
    if max(differences) > 0.002 or max(map_differences) > 0.002:
        raise RuntimeError("Export score/map parity exceeded tolerance")
    result = {
        "runtime": "ONNX Runtime CPU",
        "runtime_version": importlib.metadata.version("onnxruntime"),
        "images": len(scores),
        "max_absolute_score_difference": max(differences),
        "mean_absolute_score_difference": float(np.mean(differences)),
        "map_comparison_images": 4,
        "max_absolute_map_difference": max(map_differences),
        "tolerance": 0.002,
        "test": metrics(labels, scores, onnx.metadata["image_threshold"]),
        "inference_ms": {
            "mean": float(np.mean(latencies)),
            "p95": float(np.quantile(latencies, 0.95)),
            "scope": "Single-image preprocessing, ONNX encoder and score-map generation; excludes IO/API",
        },
        "passed": True,
    }
    assert result["test"]["confusion"] == report["test"]["confusion"]
    report["model"] = onnx.metadata
    report["deployment_validation"] = result
    for destination in [Path("reports/evaluation.json"), root / "evaluation.json"]:
        destination.write_text(json.dumps(report, indent=2) + "\n")
    Path("reports/onnx-parity.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
