"""Verification of the immutable handoff manifest plus acknowledged local changes."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath


@dataclass(frozen=True, slots=True)
class TransferVerification:
    manifest_entries: int
    exact_entries: int
    initial_exact_entries: int
    acknowledged_deviations: int
    project_developed_entries: int
    parent_snapshot_entries: int
    parent_snapshot_exact: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _local_path(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ValueError(f"Unsafe manifest path: {relative!r}")
    path = (root / Path(*pure.parts)).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"Manifest path escapes repository: {relative!r}")
    return path


def verify_transfer_snapshot(
    root: str | Path,
    *,
    manifest_relative: str = "TRANSFER_MANIFEST.json",
    receipt_relative: str = "manifests/transfer_verification_20260901.json",
) -> TransferVerification:
    """Verify the transfer snapshot while allowing only receipt-bound deviations."""

    repository = Path(root).resolve()
    manifest_path = _local_path(repository, manifest_relative)
    receipt_path = _local_path(repository, receipt_relative)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    if manifest.get("schema_version") != "milky_cow_transfer_manifest.v1":
        raise ValueError("Unsupported transfer manifest schema")
    if receipt.get("schema_version") != "milky_cow_transfer_verification.v1":
        raise ValueError("Unsupported transfer verification receipt schema")
    if sha256_file(manifest_path) != receipt["base_manifest"]["sha256"]:
        raise ValueError("Transfer manifest hash differs from the verification receipt")

    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ValueError("Transfer manifest files must be a list")
    paths = [entry.get("path") for entry in entries]
    if any(not isinstance(path, str) for path in paths) or len(paths) != len(set(paths)):
        raise ValueError("Transfer manifest paths must be unique strings")
    if manifest.get("file_count") != len(entries):
        raise ValueError("Transfer manifest file_count mismatch")
    if manifest.get("total_bytes") != sum(int(entry["bytes"]) for entry in entries):
        raise ValueError("Transfer manifest total_bytes mismatch")

    deviations_list = receipt.get("acknowledged_deviations")
    if not isinstance(deviations_list, list):
        raise ValueError("Verification receipt deviations must be a list")
    deviations = {row["path"]: row for row in deviations_list}
    if len(deviations) != len(deviations_list):
        raise ValueError("Verification receipt contains duplicate deviation paths")
    if not set(deviations).issubset(paths):
        raise ValueError("Verification receipt names a path outside the transfer manifest")
    development = receipt.get("post_verification_project_development")
    if not isinstance(development, dict):
        raise ValueError("Verification receipt lacks project-development state")
    developed_list = development.get("starter_paths")
    if (
        not isinstance(developed_list, list)
        or any(not isinstance(path, str) for path in developed_list)
        or len(developed_list) != len(set(developed_list))
    ):
        raise ValueError("Project-developed starter paths must be unique strings")
    developed_paths = set(developed_list)
    if not developed_paths.issubset(paths) or developed_paths & set(deviations):
        raise ValueError("Project-developed paths are outside or overlap deviations")

    exact = parent_total = parent_exact = acknowledged = developed = 0
    for entry in entries:
        relative = entry["path"]
        path = _local_path(repository, relative)
        exists = path.is_file()
        actual_bytes = path.stat().st_size if exists else None
        actual_hash = sha256_file(path) if exists else None
        matches = (
            exists
            and actual_bytes == int(entry["bytes"])
            and actual_hash == entry["sha256"]
        )
        if entry["origin"] == "parent_snapshot":
            parent_total += 1
            if not matches:
                raise ValueError(f"Imported parent artifact differs: {relative}")
            parent_exact += 1

        deviation = deviations.get(relative)
        is_developed = relative in developed_paths
        if deviation is None and not is_developed:
            if not matches:
                raise ValueError(f"Unacknowledged transfer difference: {relative}")
            exact += 1
            continue
        if is_developed:
            if entry["origin"] != "starter_bundle":
                raise ValueError(f"Imported parent artifact cannot be project-developed: {relative}")
            if matches:
                raise ValueError(f"Project-developed starter path is unchanged: {relative}")
            developed += 1
            continue

        if matches:
            raise ValueError(f"Receipt deviation no longer exists: {relative}")
        if deviation.get("origin") != entry["origin"]:
            raise ValueError(f"Receipt origin mismatch: {relative}")
        if not deviation.get("user_confirmed"):
            raise ValueError(f"Receipt deviation lacks user confirmation: {relative}")
        state = deviation["verified_state"]
        if bool(state["exists"]) != exists:
            raise ValueError(f"Receipt existence mismatch: {relative}")
        if exists and (
            int(state["bytes"]) != actual_bytes or state["sha256"] != actual_hash
        ):
            raise ValueError(f"Receipt byte identity mismatch: {relative}")
        acknowledged += 1

    declared = receipt["verification"]
    initial_exact = len(entries) - len(deviations)
    historical = {
        "manifest_entries": len(entries),
        "exact_entries": initial_exact,
        "acknowledged_deviations": len(deviations),
        "parent_snapshot_entries": parent_total,
        "parent_snapshot_exact": parent_exact,
    }
    for key, value in historical.items():
        if int(declared[key]) != value:
            raise ValueError(f"Receipt historical aggregate mismatch for {key}")
    if exact + acknowledged + developed != len(entries):
        raise ValueError("Current transfer-state categories do not cover the manifest")

    return TransferVerification(
        manifest_entries=len(entries),
        exact_entries=exact,
        initial_exact_entries=initial_exact,
        acknowledged_deviations=acknowledged,
        project_developed_entries=developed,
        parent_snapshot_entries=parent_total,
        parent_snapshot_exact=parent_exact,
    )

@dataclass(frozen=True, slots=True)
class ImplementationVerification:
    reviewed_sources: int
    local_artifacts: int
    derivations: int


def verify_implementation_provenance(
    root: str | Path,
    *,
    manifest_relative: str = "manifests/implementation_provenance_20260901.json",
) -> ImplementationVerification:
    """Verify every reviewed source and active local derivative by byte hash."""

    repository = Path(root).resolve()
    manifest_path = _local_path(repository, manifest_relative)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "milky_cow_implementation_provenance.v1":
        raise ValueError("Unsupported implementation provenance schema")
    source_repository = document.get("source_repository")
    if not isinstance(source_repository, dict) or source_repository.get("revision") != (
        "106cfb782c6e573856282095441bb69f23924a55"
    ):
        raise ValueError("Implementation provenance has the wrong parent revision")
    if document.get("exact_byte_code_imports") != []:
        raise ValueError("Selective derivatives must not claim exact byte-code imports")

    required_sources = {
        "reference/shared_source/io.py",
        "reference/shared_source/models.py",
        "reference/shared_source/timezones.py",
        "reference/shared_source/evaluation.py",
        "reference/shared_source/pa.py",
        "reference/shared_source/treasury.py",
        "reference/shared_source/rules.py",
    }
    required_locals = {
        "TRANSFER_MANIFEST.json",
        "manifests/transfer_verification_20260901.json",
        "manifests/rr1_import_20260829.json",
        "config/README.md",
        "config/milky_cow_study_contract.json",
        "config/milky_cow_contract_gate.json",
        "project_memory/BEGINNING_OF_A_WORK_SESSION.md",
        "project_memory/PROJECT.md",
        "project_memory/EVIDENCE.md",
        "project_memory/DECISIONS.md",
        "project_memory/ARCHITECTURE.md",
        "project_memory/STATE.md",
        "project_memory/TODO.md",
        "project_memory/TESTING.md",
        "config/payout_policies.json",
        "rules/MILKY_COW_COPY_TO_ALL_RULES.txt",
        "data/MILKY_COW_INPUT_CONTRACTS.md",
        "src/milky_cow/inputs.py",
        "src/milky_cow/evaluation_lock.py",
        "src/milky_cow/contracts.py",
        "src/milky_cow/copy_to_all.py",
        "src/milky_cow/treasury.py",
        "src/milky_cow/provenance.py",
        "scripts/verify_transfer_snapshot.py",
        "scripts/run_tests.ps1",
        "scripts/run_verified_tests.ps1",
        "tests/test_study_contract.py",
        "tests/test_evidence_and_evaluation_lock.py",
        "tests/test_copy_to_all_and_scaling.py",
        "tests/test_lifecycle_policy_contracts.py",
    }
    required_derivatives = {
        "src/milky_cow/inputs.py",
        "src/milky_cow/evaluation_lock.py",
        "src/milky_cow/contracts.py",
        "src/milky_cow/copy_to_all.py",
        "src/milky_cow/treasury.py",
    }

    def verify_rows(field: str) -> dict[str, dict[str, object]]:
        rows = document.get(field)
        if not isinstance(rows, list):
            raise ValueError(f"Implementation provenance {field} must be a list")
        by_path: dict[str, dict[str, object]] = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("path"), str):
                raise ValueError(f"Implementation provenance {field} row is invalid")
            relative = row["path"]
            if relative in by_path:
                raise ValueError(f"Duplicate implementation provenance path: {relative}")
            path = _local_path(repository, relative)
            if not path.is_file() or sha256_file(path) != row.get("sha256"):
                raise ValueError(f"Implementation provenance hash mismatch: {relative}")
            by_path[relative] = row
        return by_path

    reviewed = verify_rows("reviewed_sources")
    locals_by_path = verify_rows("local_artifacts")
    if set(reviewed) != required_sources:
        raise ValueError("Implementation provenance reviewed-source set is incomplete")
    if not required_locals.issubset(locals_by_path):
        missing = sorted(required_locals - set(locals_by_path))
        raise ValueError(f"Implementation provenance local-artifact set is incomplete: {missing}")

    derivations = document.get("derivations")
    if not isinstance(derivations, list):
        raise ValueError("Implementation provenance derivations must be a list")
    derived_paths: set[str] = set()
    for row in derivations:
        if not isinstance(row, dict) or not isinstance(row.get("local_path"), str):
            raise ValueError("Implementation provenance derivation row is invalid")
        local_path = row["local_path"]
        if local_path in derived_paths or local_path not in locals_by_path:
            raise ValueError(f"Invalid or duplicate derived local path: {local_path}")
        source_paths = row.get("reviewed_source_paths")
        if (
            not isinstance(source_paths, list)
            or not source_paths
            or any(path not in reviewed for path in source_paths)
        ):
            raise ValueError(f"Invalid reviewed-source mapping for: {local_path}")
        if not isinstance(row.get("excluded_parent_mechanics"), list):
            raise ValueError(f"Missing exclusion record for: {local_path}")
        derived_paths.add(local_path)
    if derived_paths != required_derivatives:
        raise ValueError("Implementation provenance derivative set is incomplete")

    return ImplementationVerification(
        reviewed_sources=len(reviewed),
        local_artifacts=len(locals_by_path),
        derivations=len(derivations),
    )
