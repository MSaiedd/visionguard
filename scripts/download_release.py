"""Install the checksum-pinned model and attributed reference samples from the GitHub release."""

import hashlib
import io
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

URL = "https://github.com/MSaiedd/visionguard/releases/download/v0.1.0/visionguard-surface-v1.zip"
SHA256 = "93d4331a46aff6f711003ae8a1b5fe28ec1b69443e1fc0945f84c0cdb04d4195"


def main():
    if Path("artifacts/surface-v1").exists():
        raise SystemExit(
            "An artifact already exists. Preserve or move it before installing the release."
        )
    print(
        "Downloading the noncommercial reference model and attributed KSDD2 samples...", flush=True
    )
    with urlopen(URL, timeout=180) as response:
        raw = response.read(125 * 1024 * 1024 + 1)
    if len(raw) > 125 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != SHA256:
        raise SystemExit("Release checksum mismatch; no files were installed.")
    with tempfile.TemporaryDirectory(prefix="visionguard-release-") as temporary:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > 200 * 1024 * 1024:
                raise SystemExit("Release exceeds extraction budget.")
            for entry in archive.infolist():
                name = PurePosixPath(entry.filename)
                if (
                    name.is_absolute()
                    or ".." in name.parts
                    or tuple(name.parts[:2])
                    not in {("artifacts", "surface-v1"), ("data", "samples")}
                ):
                    raise SystemExit("Unexpected archive path.")
                target = Path(temporary).joinpath(*name.parts)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(entry))
        for relative in ["artifacts/surface-v1", "data/samples"]:
            target = Path(relative)
            if target.exists():
                if relative == "data/samples":
                    continue
                raise SystemExit("Destination already exists.")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(Path(temporary) / relative), target)
    print(
        "Installed surface-v1 and reference samples. See DATA_LICENSE.md for CC BY-NC-SA 4.0 terms."
    )


if __name__ == "__main__":
    main()
