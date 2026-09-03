"""Build the byte-level transfer manifest for this temporary starter bundle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARENT_COMMIT = "106cfb782c6e573856282095441bb69f23924a55"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_path(relative: str) -> str | None:
    direct_paths = (
        "config/legacy_25k_baseline.json",
        "config/payout_policies.json",
        "data/processed/README.md",
        "manifests/rr1_import_20260829.json",
        "manifests/upstream_evidence_20260829.json",
        "rules/25k_legacy_rules.txt",
        "rules/EV-account_rules.txt",
        "rules/LEGACY_25K_AUDIT.md",
        "rules/Payout_rules.txt",
        "tests/fixtures/evaluation/eodmae_legacy_25k_x3_behavior_lock.json",
    )
    if relative == "data/INPUT_CONTRACTS_FROM_PARENT.md":
        return "data/INPUT_CONTRACTS.md"
    if relative == "reference/RR_r_MFE_buy-stop-entry(EXAMPLE).cs":
        return "RR_r_MFE_buy-stop-entry(EXAMPLE).cs"
    if relative.startswith("reference/shared_source/"):
        return "src/eval_pa_optimal_path/" + relative.rsplit("/", 1)[1]
    if relative.startswith("reference/shared_tests/"):
        return "tests/" + relative.rsplit("/", 1)[1]
    if relative.startswith("data/raw/") or relative in direct_paths:
        return relative
    return None


def main() -> None:
    entries = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.name == "TRANSFER_MANIFEST.json":
            continue
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(ROOT).as_posix()
        parent_path = source_path(relative)
        entries.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "origin": "parent_snapshot" if parent_path else "starter_bundle",
                "parent_path": parent_path,
            }
        )

    payload = {
        "schema_version": "milky_cow_transfer_manifest.v1",
        "source_repository": "I:\\PycharmProjects\\Eval_PA_optimal_path",
        "source_branch": "master",
        "source_commit": PARENT_COMMIT,
        "manifest_excludes_itself": True,
        "file_count": len(entries),
        "total_bytes": sum(entry["bytes"] for entry in entries),
        "files": entries,
    }
    (ROOT / "TRANSFER_MANIFEST.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
