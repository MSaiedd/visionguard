"""Fetch the original ViCoS archive; images remain under ignored data/ with upstream terms."""

import hashlib
import json
import time
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

URL = "https://data.vicos.si/datasets/KSDD/KolektorSDD2.zip"


def main():
    root = Path("data/ksdd2")
    root.mkdir(parents=True, exist_ok=True)
    archive = Path("data/KolektorSDD2.zip")
    if not archive.exists():
        temporary = archive.with_suffix(".partial")
        offset = temporary.stat().st_size if temporary.exists() else 0
        request = Request(URL, headers={"Range": f"bytes={offset}-"} if offset else {})
        with urlopen(request, timeout=120) as response:
            if offset and response.status != 206:
                offset = 0
            with temporary.open("ab" if offset else "wb") as out:
                total = offset
                last = time.monotonic()
                while block := response.read(1024 * 1024):
                    out.write(block)
                    total += len(block)
                    if time.monotonic() - last > 10:
                        print(f"Downloaded {total / 1024**2:.1f} MiB", flush=True)
                        last = time.monotonic()
        temporary.rename(archive)
    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != "edcdb486809b24f1d17b785e30c52fafc5999554dd5fe18ddf77b61ceb6f36a8":
        raise ValueError("Original archive differs from the pinned dataset checksum")
    with zipfile.ZipFile(archive) as z:
        assert sum(f.file_size for f in z.infolist()) < 2 * 1024**3
        for entry in z.infolist():
            name = Path(entry.filename)
            if name.is_absolute() or ".." in name.parts:
                raise ValueError("Unsafe archive path")
            if not entry.is_dir() and name.suffix.lower() in {".png", ".txt"}:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_bytes(z.read(entry))
    manifest = {
        "source": URL,
        "homepage": "https://www.vicos.si/resources/kolektorsdd2/",
        "license": "CC BY-NC-SA 4.0",
        "archive_sha256": hashlib.file_digest(archive.open("rb"), "sha256").hexdigest(),
    }
    (root / "source.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest), flush=True)


if __name__ == "__main__":
    main()
