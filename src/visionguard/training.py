"""Fit a normal-reference model, select thresholds on validation, and evaluate untouched test images."""

import argparse
import hashlib
import importlib.metadata
import json
import random
import time
from pathlib import Path

import numpy as np
from PIL import Image
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
)

from .model import image_scores, image_tensor, make_encoder, patch_distances, smooth_maps


def records(root, split):
    result = []
    for image in sorted((Path(root) / split).glob("*.png")):
        if " (copy)" in image.stem:
            original = image.with_name(image.name.replace(" (copy)", ""))
            if not original.exists() or image.read_bytes() != original.read_bytes():
                raise ValueError("Unverified duplicate in source archive")
            continue
        if image.stem.endswith("_GT"):
            continue
        mask = image.with_name(image.stem + "_GT.png")
        if not mask.exists():
            raise ValueError(f"Missing mask for {image.name}")
        with Image.open(mask) as im:
            positive = bool(np.array(im).max())
        result.append(
            {
                "id": split + "/" + image.name,
                "image": str(image),
                "mask": str(mask),
                "label": int(positive),
            }
        )
    if not result:
        raise ValueError("No dataset images; run scripts/download_data.py")
    return result


def split_training(rows, seed=42):
    rng = random.Random(seed)
    train = []
    validation = []
    for label in (0, 1):
        group = [r for r in rows if r["label"] == label]
        rng.shuffle(group)
        n = max(1, round(len(group) * 0.2))
        validation.extend(group[:n])
        train.extend(group[n:])
    return sorted(train, key=lambda r: r["id"]), sorted(validation, key=lambda r: r["id"])


def best_threshold(labels, scores):
    precision, recall, thresholds = precision_recall_curve(labels, scores)
    f1 = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-10)
    return float(thresholds[int(np.argmax(f1))])


def metrics(labels, scores, threshold):
    predictions = np.asarray(scores) >= threshold
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel().tolist()
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    return {
        "images": len(labels),
        "positive_images": int(sum(labels)),
        "auroc": float(roc_auc_score(labels, scores)),
        "average_precision": float(average_precision_score(labels, scores)),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / max(precision + recall, 1e-10),
        "confusion": {
            "true_negative": tn,
            "false_positive": fp,
            "false_negative": fn,
            "true_positive": tp,
        },
    }


def main():
    import torch
    from safetensors.torch import save_file

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/ksdd2")
    parser.add_argument("--output", default="artifacts/surface-v1")
    parser.add_argument("--max-normal", type=int, default=1000)
    parser.add_argument("--dimensions", type=int, default=48)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    if args.max_normal < 2 or not 1 <= args.dimensions <= 448 or not 1 <= args.batch_size <= 64:
        parser.error("Use at least two normal images, 1–448 dimensions and batch size 1–64")
    torch.set_num_threads(2)
    torch.manual_seed(42)
    train, validation = split_training(records(args.data, "train"))
    test = records(args.data, "test")
    normal = [r for r in train if not r["label"]]
    random.Random(42).shuffle(normal)
    normal = normal[: args.max_normal]
    encoder = make_encoder(True)
    indices = torch.randperm(448)[: args.dimensions].sort().values
    height, width = 320, 128
    started = time.perf_counter()
    sums = outer = None
    count = 0

    def batches(rows):
        for i in range(0, len(rows), args.batch_size):
            chunk = rows[i : i + args.batch_size]
            tensors = []
            for row in chunk:
                with Image.open(row["image"]) as im:
                    tensors.append(image_tensor(im, height, width))
            yield chunk, torch.stack(tensors)

    with torch.inference_mode():
        for chunk, images in batches(normal):
            features = encoder(images)[:, indices]
            grid = tuple(features.shape[-2:])
            x = features.flatten(2)
            total = x.sum(0).double()
            second = torch.einsum("bcp,bdp->pcd", x, x).double()
            sums = total if sums is None else sums + total
            outer = second if outer is None else outer + second
            count += len(chunk)
            if count % 80 == 0:
                print(
                    json.dumps({"stage": "fit", "images": count, "total": len(normal)}), flush=True
                )
        mean = sums / count
        covariance = (outer - count * torch.einsum("cp,dp->pcd", mean, mean)) / (count - 1)
        # Shrinkage stabilizes small eigenvalues in each spatial Gaussian.
        covariance += torch.eye(args.dimensions)[None] * 0.05
        precision = torch.linalg.inv(covariance).float()
        mean = mean.float()

        def evaluate(rows, label):
            labels = []
            scores = []
            pixel_labels = []
            pixel_scores = []
            latencies = []
            examples = []
            for chunk, images in batches(rows):
                tick = time.perf_counter()
                features = encoder(images)[:, indices].flatten(2)
                maps = smooth_maps(patch_distances(features, mean, precision), grid, height, width)
                elapsed = (time.perf_counter() - tick) * 1000 / len(chunk)
                for row, values, score in zip(chunk, maps, image_scores(maps), strict=True):
                    with Image.open(row["mask"]) as im:
                        mask = np.array(im.resize((width, height), Image.Resampling.NEAREST)) > 0
                    labels.append(row["label"])
                    scores.append(float(score))
                    latencies.append(elapsed)
                    # Fixed stride for bounded pixel evaluation memory; never select pixels by their labels.
                    pixel_labels.append(mask[::4, ::4].reshape(-1))
                    pixel_scores.append(values[::4, ::4].reshape(-1))
                    examples.append({"id": row["id"], "label": row["label"], "score": float(score)})
                if len(labels) % 80 == 0:
                    print(
                        json.dumps({"stage": label, "images": len(labels), "total": len(rows)}),
                        flush=True,
                    )
            return (
                labels,
                scores,
                np.concatenate(pixel_labels),
                np.concatenate(pixel_scores),
                latencies,
                examples,
            )

        vl, vs, vpl, vps, _, _ = evaluate(validation, "validation")
        threshold = best_threshold(vl, vs)
        pixel_threshold = best_threshold(vpl, vps)
        tl, ts, tpl, tps, times, examples = evaluate(test, "test")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    state = {"encoder." + k: v.contiguous() for k, v in encoder.state_dict().items()}
    state.update(
        mean=mean.contiguous(), precision=precision.contiguous(), indices=indices.contiguous()
    )
    save_file(state, str(output / "model.safetensors"))
    metadata = {
        "schema_version": 1,
        "version": "surface-v1-"
        + hashlib.sha256((output / "model.safetensors").read_bytes()).hexdigest()[:8],
        "method": "PaDiM-style patch Gaussian",
        "backbone": "ResNet18 IMAGENET1K_V1",
        "feature_layers": ["layer1", "layer2", "layer3"],
        "dimensions": args.dimensions,
        "input_size": [height, width],
        "image_threshold": threshold,
        "pixel_threshold": pixel_threshold,
        "heatmap_low": float(np.quantile(vps, 0.5)),
        "heatmap_high": float(np.quantile(vps, 0.999)),
        "weights_sha256": hashlib.sha256((output / "model.safetensors").read_bytes()).hexdigest(),
        "license": "CC BY-NC-SA 4.0 reference-data terms; research/portfolio use",
        "dataset": "KolektorSDD2",
        "fitted_normal_images": len(normal),
        "score_definition": "99.5th percentile of smoothed patch Mahalanobis distances; not a probability",
    }
    (output / "model.json").write_text(json.dumps(metadata, indent=2) + "\n")
    report = {
        "schema_version": 1,
        "model": metadata,
        "seed": 42,
        "train_images": len(train),
        "fitted_normal_images": len(normal),
        "validation": metrics(vl, vs, threshold),
        "test": metrics(tl, ts, threshold),
        "pixel_test_auroc": float(roc_auc_score(tpl, tps)),
        "pixel_test_average_precision": float(average_precision_score(tpl, tps)),
        "pixel_evaluation": "Fixed stride 4 on resized 320×128 mask; not full-resolution benchmark",
        "latency_ms": {
            "mean": float(np.mean(times)),
            "p95": float(np.quantile(times, 0.95)),
            "batch_size": args.batch_size,
            "includes": "batched encoder and score map, excludes disk IO/API",
        },
        "elapsed_seconds": time.perf_counter() - started,
        "normal_training_ids": [r["id"] for r in normal],
        "validation_ids": [r["id"] for r in validation],
        "test_predictions": examples,
        "dataset_manifest": json.loads((Path(args.data) / "source.json").read_text()),
        "versions": {
            n: importlib.metadata.version(n)
            for n in ["torch", "torchvision", "numpy", "scikit-learn"]
        },
        "limits": "Official train/test partition, stratified image-level validation. Physical-item grouping unavailable; no general manufacturing or out-of-domain accuracy claim.",
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    from .model import export_serving

    report["model"] = export_serving(output)
    Path("reports/evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "test": report["test"],
                "pixel_test_auroc": report["pixel_test_auroc"],
                "seconds": report["elapsed_seconds"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
