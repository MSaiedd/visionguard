"""PaDiM-style normal-patch distributions over frozen pretrained ResNet18 features.

The fitted Gaussian statistics are learned from normal training images. No defect-type
classifier, synthetic predictions or language model is used in the serving path.
"""

import hashlib
import json
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage


def image_array(image, height=320, width=128):

    image = (
        ImageOps.exif_transpose(image)
        .convert("RGB")
        .resize((width, height), Image.Resampling.BILINEAR)
    )
    values = np.array(image, dtype=np.float32) / 255.0
    values = (values - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
        [0.229, 0.224, 0.225], dtype=np.float32
    )
    return values.transpose(2, 0, 1).copy()


def image_tensor(image, height=320, width=128):
    import torch

    return torch.from_numpy(image_array(image, height, width))


def make_encoder(pretrained=False):
    from torch import nn
    from torchvision.models import ResNet18_Weights, resnet18

    class Encoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.network = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1 if pretrained else None)

        def forward(self, x):
            import torch.nn.functional as F

            n = self.network
            x = n.maxpool(n.relu(n.bn1(n.conv1(x))))
            a = n.layer1(x)
            b = n.layer2(a)
            c = n.layer3(b)
            import torch

            return torch.cat(
                [
                    a,
                    F.interpolate(b, size=a.shape[-2:], mode="nearest"),
                    F.interpolate(c, size=a.shape[-2:], mode="nearest"),
                ],
                dim=1,
            )

    return Encoder().eval()


def patch_distances(features, mean, precision):
    import torch

    # Inputs: batch × channels × patches. Precision: patches × channels × channels.
    delta = features - mean[None]
    values = torch.einsum("bcp,pcd,bdp->bp", delta, precision, delta)
    return values.clamp_min(0).sqrt()


def smooth_maps(distances, grid, height, width):
    import torch.nn.functional as F

    maps = F.interpolate(
        distances.reshape(-1, 1, *grid), size=(height, width), mode="bilinear", align_corners=False
    )[:, 0].numpy()
    return np.stack([ndimage.gaussian_filter(value, sigma=3) for value in maps])


def image_scores(maps):
    # A high percentile reduces single-pixel noise while retaining localized defects.
    return np.quantile(maps.reshape(len(maps), -1), 0.995, axis=1)


def regions_from_map(values, threshold, original_size):
    binary = values >= threshold
    labels, count = ndimage.label(binary)
    boxes = []
    height, width = values.shape
    ow, oh = original_size
    for label in range(1, count + 1):
        ys, xs = np.where(labels == label)
        if len(xs) < 8:
            continue
        boxes.append(
            {
                "label": "Surface anomaly",
                "x": round(int(xs.min()) / width * ow),
                "y": round(int(ys.min()) / height * oh),
                "width": max(1, round((int(xs.max()) + 1 - int(xs.min())) / width * ow)),
                "height": max(1, round((int(ys.max()) + 1 - int(ys.min())) / height * oh)),
                "peak_score": round(float(values[ys, xs].max()), 4),
                "area_fraction": round(len(xs) / (height * width), 6),
            }
        )
    return sorted(boxes, key=lambda b: b["peak_score"], reverse=True)[:30]


def render_heatmap(image, values, low, high):
    """Transparent fixed-scale heat overlay; colors are comparable across inspections."""
    normalized = np.clip((values - low) / max(high - low, 1e-6), 0, 1)
    stops = np.array(
        [[17, 54, 62], [20, 119, 117], [169, 207, 91], [251, 194, 70], [235, 91, 59]],
        dtype=np.float32,
    )
    positions = normalized * 4
    left = np.floor(positions).astype(int).clip(0, 3)
    mix = (positions - left)[..., None]
    rgb = stops[left] * (1 - mix) + stops[left + 1] * mix
    alpha = (normalized**1.6 * 0.75 * 255).astype(np.uint8)
    overlay = Image.fromarray(np.dstack([rgb.astype(np.uint8), alpha]), "RGBA").resize(
        image.size, Image.Resampling.BILINEAR
    )
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


class TorchInspector:
    def __init__(self, directory):
        import torch
        from safetensors.torch import load_file

        torch.set_num_threads(2)
        root = Path(directory)
        self.metadata = json.loads((root / "model.json").read_text())
        raw = root / "model.safetensors"
        if hashlib.sha256(raw.read_bytes()).hexdigest() != self.metadata["weights_sha256"]:
            raise ValueError("Model checksum mismatch")
        state = load_file(str(raw))
        self.encoder = make_encoder()
        self.encoder.load_state_dict(
            {k.removeprefix("encoder."): v for k, v in state.items() if k.startswith("encoder.")}
        )
        self.mean = state["mean"]
        self.precision = state["precision"]
        self.indices = state["indices"].long()
        self.lock = threading.Lock()
        self.torch = torch
        self.height, self.width = self.metadata["input_size"]
        self.version = self.metadata["version"]

    def predict(self, image):
        import time

        started = time.perf_counter()
        with self.lock, self.torch.inference_mode():
            features = self.encoder(image_tensor(image, self.height, self.width)[None])[
                :, self.indices
            ]
            grid = features.shape[-2:]
            distances = patch_distances(features.flatten(2), self.mean, self.precision)
            values = smooth_maps(distances, grid, self.height, self.width)[0]
        score = float(image_scores(values[None])[0])
        threshold = self.metadata["image_threshold"]
        # Near-threshold images are explicitly referred for review.
        ratio = score / threshold if threshold else 0
        decision = (
            "review" if 0.9 <= ratio <= 1.1 else ("suspect" if score >= threshold else "clear")
        )
        return {
            "score": round(score, 4),
            "threshold": threshold,
            "decision": decision,
            "regions": regions_from_map(values, self.metadata["pixel_threshold"], image.size),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "model_version": self.version,
            "map": values,
        }


def numpy_maps(features, mean, precision, height, width):
    """Equivalent deployed CPU score path, with no PyTorch runtime dependency."""
    grid = features.shape[-2:]
    delta = features.reshape(len(features), features.shape[1], -1) - mean[None]
    distance = np.sqrt(
        np.maximum(np.einsum("bcp,pcd,bdp->bp", delta, precision, delta, optimize=True), 0)
    )
    values = []
    for row in distance:
        expanded = ndimage.zoom(
            row.reshape(grid),
            (height / grid[0], width / grid[1]),
            order=1,
            mode="nearest",
            grid_mode=True,
        )
        values.append(ndimage.gaussian_filter(expanded, sigma=3))
    return np.stack(values)


class Inspector:
    """Checksum-verified ONNX encoder plus learned Gaussian statistics for lightweight serving."""

    def __init__(self, directory):
        import onnxruntime as ort
        from threadpoolctl import threadpool_limits

        threadpool_limits(limits=2)
        root = Path(directory)
        self.metadata = json.loads((root / "model.json").read_text())
        for filename, key in [
            ("encoder.onnx", "encoder_sha256"),
            ("reference.npz", "reference_sha256"),
        ]:
            if hashlib.sha256((root / filename).read_bytes()).hexdigest() != self.metadata[key]:
                raise ValueError("Serving artifact checksum mismatch")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(root / "encoder.onnx"), sess_options=options, providers=["CPUExecutionProvider"]
        )
        with np.load(root / "reference.npz", allow_pickle=False) as reference:
            self.mean = reference["mean"]
            self.precision = reference["precision"]
            self.indices = reference["indices"]
        self.height, self.width = self.metadata["input_size"]
        self.version = self.metadata["version"]
        self.lock = threading.Lock()

    def predict(self, image):
        import time

        started = time.perf_counter()
        with self.lock:
            inputs = image_array(image, self.height, self.width)[None]
            features = self.session.run(None, {"image": inputs})[0][:, self.indices]
            values = numpy_maps(features, self.mean, self.precision, self.height, self.width)[0]
        score = float(image_scores(values[None])[0])
        threshold = self.metadata["image_threshold"]
        ratio = score / threshold if threshold else 0
        return {
            "score": round(score, 4),
            "threshold": threshold,
            "decision": "review"
            if 0.9 <= ratio <= 1.1
            else ("suspect" if score >= threshold else "clear"),
            "regions": regions_from_map(values, self.metadata["pixel_threshold"], image.size),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "model_version": self.version,
            "map": values,
        }


def export_serving(directory):
    """Export exactly the evaluated encoder/statistics. Exporting never refits the model."""
    import torch
    from safetensors.torch import load_file

    root = Path(directory)
    metadata = json.loads((root / "model.json").read_text())
    state = load_file(str(root / "model.safetensors"))
    encoder = make_encoder()
    encoder.load_state_dict(
        {k.removeprefix("encoder."): v for k, v in state.items() if k.startswith("encoder.")}
    )
    height, width = metadata["input_size"]
    torch.onnx.export(
        encoder,
        torch.zeros(1, 3, height, width),
        str(root / "encoder.onnx"),
        input_names=["image"],
        output_names=["features"],
        opset_version=17,
        dynamo=False,
    )
    np.savez_compressed(
        root / "reference.npz",
        mean=state["mean"].numpy(),
        precision=state["precision"].numpy(),
        indices=state["indices"].numpy(),
    )
    encoder_sha = hashlib.sha256((root / "encoder.onnx").read_bytes()).hexdigest()
    reference_sha = hashlib.sha256((root / "reference.npz").read_bytes()).hexdigest()
    metadata.update(
        training_checkpoint_sha256=metadata["weights_sha256"],
        encoder_sha256=encoder_sha,
        reference_sha256=reference_sha,
        runtime="ONNX Runtime CPU",
    )
    metadata["version"] = (
        "surface-v1-" + hashlib.sha256((encoder_sha + reference_sha).encode()).hexdigest()[:8]
    )
    (root / "model.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata
