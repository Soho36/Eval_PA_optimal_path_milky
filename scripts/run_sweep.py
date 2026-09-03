"""Execute the N x payout-policy sweep and write its result manifests.

    python scripts/run_sweep.py                 # full 20 x 6 central arm
    python scripts/run_sweep.py --n 1 2 3       # a subset of the N axis
    python scripts/run_sweep.py --workers 4

Writes a per-arm summary JSON and a per-cohort CSV. The sweep aggregates; it
does not rank policies or draw conclusions, and the manifest carries the gate's
remaining blockers so a reader cannot mistake it for a finished study.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from multiprocessing import Pool
import platform
import subprocess
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from milky_cow.inputs import load_verified_rr1_dataset  # noqa: E402
from milky_cow.policy_bundle import load_policy_bundle  # noqa: E402
from milky_cow.sweep import build_grid, init_worker, run_arm_task  # noqa: E402

RESULTS = ROOT / "results"


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, cwd=ROOT, check=True
        ).stdout.strip()
    except Exception:
        return ""


def run_identity() -> dict:
    """Everything needed to say which code produced this output.

    The working-tree digest hashes the *contents* of every modified file, not
    the `git status` text: two different edits to the same paths produced the
    same digest before this.
    """

    dirty = _git("status", "--porcelain")
    paths = sorted(
        line[2:].strip().split(" -> ")[-1]
        for line in dirty.splitlines()
        if line[2:].strip()
    )
    digest = hashlib.sha256()
    tracked: list[dict] = []
    for relative in paths:
        digest.update(relative.encode("utf-8"))
        digest.update(b"|")
        candidate = ROOT / relative
        if candidate.is_file():
            blob = hashlib.sha256(candidate.read_bytes()).hexdigest()
            digest.update(blob.encode("utf-8"))
            tracked.append({"path": relative, "sha256": blob})
        else:
            digest.update(b"absent-or-directory")
        digest.update(b"\n")
    return {
        "git_revision": _git("rev-parse", "HEAD"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "working_tree_dirty": bool(dirty),
        "working_tree_digest_sha256": digest.hexdigest(),
        "dirty_files": tracked,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, nargs="*", default=list(range(1, 21)))
    parser.add_argument("--policies", nargs="*", default=None)
    parser.add_argument("--path-arm", default=None)
    parser.add_argument("--event-order", default=None)
    parser.add_argument(
        "--execution",
        nargs="*",
        default=None,
        help="execution model ids; defaults to the configured model only",
    )
    parser.add_argument("--workers", type=int, default=7)
    parser.add_argument("--tag", default="central")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing artifact with this tag instead of refusing",
    )
    parser.add_argument(
        "--exploratory",
        action="store_true",
        help="run despite the gate's outstanding blockers and label the output",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = json.loads(
        (ROOT / "config" / "runtime.json").read_text(encoding="utf-8")
    )
    policies = args.policies or config["payout"]["policy_ids"]
    path_arm = args.path_arm or config["intratrade_path_order"]["central_arm"]
    event_order = args.event_order or config["event_order"]["selected"]
    execution_ids = args.execution or [config["execution"]["selected_model_id"]]

    # One bundle up front so a misconfigured grid fails before the workers start.
    probe = load_policy_bundle(
        ROOT,
        target_active_pas=args.n[0],
        payout_policy_id=policies[0],
        path_stress_arm=path_arm,
        event_order_mode=event_order,
        execution_model_id=execution_ids[0],
        exploratory=args.exploratory,
    )
    dataset = load_verified_rr1_dataset(ROOT / "data" / "raw" / "rr1")

    grid = build_grid(
        args.n,
        policies,
        path_stress_arm=path_arm,
        event_order_mode=event_order,
        execution_model_ids=execution_ids,
        exploratory=args.exploratory,
    )
    print(
        f"sweep: {len(args.n)} N x {len(policies)} policies = {len(grid)} arms"
        f" on {args.workers} workers"
    )

    started = time.time()
    payloads: list[dict] = []
    with Pool(
        processes=args.workers,
        initializer=init_worker,
        initargs=(str(ROOT), probe.horizon_days),
    ) as pool:
        for index, payload in enumerate(
            pool.imap_unordered(run_arm_task, grid), start=1
        ):
            payloads.append(payload)
            summary = payload["summary"]
            print(
                f"  [{index:3d}/{len(grid)}] N={summary['n']:2d}"
                f" {summary['payout_policy_id']:<20}"
                f" median ${summary['owner_net_retained_cash_usd']['median']:>9,.0f}"
                f" positive {summary['owner_net_retained_cash_usd']['positive_cohorts']:>2d}"
                f"/{summary['cohort_count']}",
                flush=True,
            )
    elapsed = time.time() - started

    # Scheduling is nondeterministic; the manifest must not be.
    summaries = sorted(
        (payload["summary"] for payload in payloads),
        key=lambda row: (
            row["n"],
            row["payout_policy_id"],
            row["execution_model_id"],
        ),
    )
    cohort_rows = sorted(
        (row for payload in payloads for row in payload["cohorts"]),
        key=lambda row: (
            row["n"],
            row["payout_policy_id"],
            row["execution_model_id"],
            row["start_at"],
        ),
    )

    manifest = {
        "schema_version": "milky_cow_sweep.v1",
        "status": (
            "exploratory_run_gate_blockers_outstanding"
            if probe.exploratory
            else "aggregated_grid_not_a_ranked_conclusion"
        ),
        "outstanding_blockers_at_run_time": list(probe.outstanding_blockers),
        "grid": {
            "n_values": args.n,
            "payout_policy_ids": list(policies),
            "path_stress_arm": path_arm,
            "event_order_mode": event_order,
            "execution_model_ids": execution_ids,
            "arms": len(grid),
            "cohorts_per_arm": summaries[0]["cohort_count"],
            "total_cohort_runs": sum(row["cohort_count"] for row in summaries),
            "runtime_seconds": round(elapsed, 1),
            "workers": args.workers,
        },
        "provenance": {
            "config_sha256": probe.config_sha256,
            "accepted_stream_sha256": dataset.selection.accepted_stream_sha256,
            "horizon_days": probe.horizon_days,
        },
        "arms": summaries,
    }
    # The digest covers the cohort rows too, not only the arm summaries: the
    # CSV is a first-class output and belongs inside the seal.
    manifest["result_digest_sha256"] = hashlib.sha256(
        json.dumps(
            {"arms": summaries, "cohorts": cohort_rows}, sort_keys=True
        ).encode("utf-8")
    ).hexdigest()
    manifest["run_identity"] = run_identity()

    RESULTS.mkdir(parents=True, exist_ok=True)
    summary_path = RESULTS / f"sweep_{args.tag}_summary.json"
    cohort_path = RESULTS / f"sweep_{args.tag}_cohorts.csv"
    if not args.overwrite and (summary_path.exists() or cohort_path.exists()):
        raise SystemExit(
            f"refusing to overwrite an existing artifact for tag '{args.tag}'; "
            "choose a new --tag or pass --overwrite"
        )
    with cohort_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cohort_rows[0]))
        writer.writeheader()
        writer.writerows(cohort_rows)

    # Hash every output file before sealing the manifest that names them.
    manifest["output_files"] = {
        cohort_path.name: {
            "sha256": hashlib.sha256(cohort_path.read_bytes()).hexdigest(),
            "bytes": cohort_path.stat().st_size,
            "rows": len(cohort_rows),
        }
    }
    summary_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"\n{len(grid)} arms in {elapsed / 60:.1f} min")
    print(f"  wrote {summary_path.relative_to(ROOT)}")
    print(f"  wrote {cohort_path.relative_to(ROOT)} ({len(cohort_rows)} rows)")
    print(f"  digest {manifest['result_digest_sha256'][:16]}")


if __name__ == "__main__":
    main()
