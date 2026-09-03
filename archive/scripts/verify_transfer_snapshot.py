"""Verify the immutable transfer manifest with acknowledged post-transfer changes."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from milky_cow.provenance import verify_transfer_snapshot


def main() -> None:
    result = verify_transfer_snapshot(ROOT)
    print(
        f"Verified {result.parent_snapshot_exact}/{result.parent_snapshot_entries} "
        f"imported parent artifacts; {result.exact_entries}/{result.manifest_entries} "
        f"entries remain byte-identical, {result.project_developed_entries} starter "
        f"entries are project-developed, and {result.acknowledged_deviations} "
        "user-confirmed starter deviations remain."
    )


if __name__ == "__main__":
    main()
