"""Execute the N=1 real-tape slice and write its result manifest.

This is the milestone that proves the gate, the cycle-local Evaluation
consumer, and the lifecycle compose over the real RR1 tape. It is deliberately
one N value and one payout policy: it is not the study, and the manifest says
so in its own status field.

    python scripts/run_n1_manifest.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import statistics as stats
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from milky_cow.cohorts import first_session_monthly_cohorts  # noqa: E402
from milky_cow.inputs import load_verified_rr1_dataset, money  # noqa: E402
from milky_cow.policy_bundle import load_policy_bundle  # noqa: E402
from milky_cow.study_runner import run_cohort  # noqa: E402

PAYOUT_POLICY_ID = "minimum_500_always"
OUTPUT = ROOT / "results" / "n1_real_tape_slice.json"


def main() -> None:
    dataset = load_verified_rr1_dataset(ROOT / "data" / "raw" / "rr1")
    bundle = load_policy_bundle(
        ROOT, target_active_pas=1, payout_policy_id=PAYOUT_POLICY_ID
    )
    selection = first_session_monthly_cohorts(
        dataset.selection.accepted_opportunities, horizon_days=bundle.horizon_days
    )

    started = time.time()
    results = [run_cohort(bundle, dataset, cohort) for cohort in selection.cohorts]
    elapsed = time.time() - started

    retained = [row.owner_net_retained_cash_usd for row in results]
    harvest = [row.cumulative_payout_harvest_usd for row in results]
    manifests = [row.as_manifest() for row in results]
    payload = {
        "schema_version": "milky_cow_n1_slice.v1",
        "status": "executable_slice_not_a_study_result",
        "what_this_is_not": [
            "not a policy ranking: one payout candidate of six was run",
            "not an N comparison: only N=1 was run",
            "not conclusive on economics: the required one-tick-per-side "
            "execution sensitivity has not been implemented",
        ],
        "arm": {
            "arm_id": bundle.arm_id,
            "target_active_pas": bundle.target_active_pas,
            "payout_policy_id": PAYOUT_POLICY_ID,
            "path_stress_arm": bundle.path_stress_arm,
            "event_order_mode": bundle.event_order_mode,
        },
        "provenance": {
            "gate_sha256": bundle.config_sha256,
            "accepted_stream_sha256": dataset.selection.accepted_stream_sha256,
            "raw_offer_count": dataset.selection.raw_count,
            "accepted_opportunity_count": len(dataset.selection.accepted),
        },
        "cohorts": {
            "cadence": "first accepted-opportunity session of each calendar month",
            "horizon_days": bundle.horizon_days,
            "complete_cohorts": len(results),
            "all_represented_months": selection.all_count,
            "runtime_seconds": round(elapsed, 2),
            "seconds_per_cohort": round(elapsed / len(results), 3),
        },
        "headline_owner_net_retained_cash_usd": {
            "median": money(stats.median(retained)),
            "minimum": money(min(retained)),
            "maximum": money(max(retained)),
            "positive_cohorts": sum(1 for value in retained if value > 0),
            "cohort_count": len(retained),
        },
        "secondary_cumulative_payout_harvest_usd": {
            "median": money(stats.median(harvest)),
            "maximum": money(max(harvest)),
            "total": money(sum(harvest)),
        },
        "pipeline_totals": {
            "pas_activated": sum(row.pas_activated for row in results),
            "pa_deaths": sum(row.pa_deaths for row in results),
            "cohorts_with_a_survivor": sum(
                1 for row in results if row.surviving_pa_count
            ),
            "evaluations_purchased": sum(row.evaluations_purchased for row in results),
            "evaluation_renewals_paid": sum(
                row.evaluation_renewals_paid for row in results
            ),
        },
        "payout_totals": {
            "executed": sum(row.payouts_executed for row in results),
            "deferred_open_copy": sum(
                row.payouts_deferred_open_copy for row in results
            ),
            "deferral_note": (
                "a PA with an open copy batch at the 23:59 close defers "
                "independently; unaffected PAs stay eligible"
            ),
        },
        "right_censoring": {
            "surviving_unwithdrawn_equity_usd": money(
                sum(row.surviving_unwithdrawn_equity_usd for row in results)
            ),
            "horizon_open_batches": sum(row.horizon_open_batches for row in results),
            "note": "never summed into the headline metric",
        },
        "cohort_results": manifests,
    }
    payload["result_digest_sha256"] = hashlib.sha256(
        json.dumps(manifests, sort_keys=True).encode("utf-8")
    ).hexdigest()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    print(f"  {len(results)} cohorts in {elapsed:.1f}s")
    print(f"  digest {payload['result_digest_sha256'][:16]}")


if __name__ == "__main__":
    main()
