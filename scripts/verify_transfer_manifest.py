"""Verify every file recorded in TRANSFER_MANIFEST.json."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    manifest = json.loads(
        (ROOT / "TRANSFER_MANIFEST.json").read_text(encoding="utf-8")
    )
    failures = []
    for entry in manifest["files"]:
        path = ROOT / entry["path"]
        if not path.is_file():
            failures.append(f"missing: {entry['path']}")
            continue
        if path.stat().st_size != entry["bytes"]:
            failures.append(f"size: {entry['path']}")
        if sha256(path) != entry["sha256"]:
            failures.append(f"sha256: {entry['path']}")
    if failures:
        raise SystemExit("Transfer verification failed:\n" + "\n".join(failures))
    print(
        f"Verified {manifest['file_count']} files "
        f"({manifest['total_bytes']} bytes) from {manifest['source_commit']}."
    )


if __name__ == "__main__":
    main()
