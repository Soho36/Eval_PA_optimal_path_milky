"""Aggregate execution cost applied to every filled contract.

Phase 1 selected a frictionless central arm, but the gate requires a
one-tick-per-side sensitivity before any headline conclusion about N. That arm
was previously unbuildable: the lifecycle accepted a single literal and raised
on anything else. This module makes execution an explicit, priced input.

Slippage is charged per side. The entry side is paid the moment the position is
opened, so it lowers the modelled intratrade excursion and can therefore change
whether an account dies mid-trade. The exit side is paid at the close. Both
sides appear in realized net P&L.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

# MNQ moves $2.00 per index point with a 0.25-point minimum tick.
MNQ_TICK_VALUE_USD = 0.50


@dataclass(frozen=True, slots=True)
class ExecutionModel:
    """One priced execution assumption, shared by the Evaluation and PA phases."""

    model_id: str
    slippage_ticks_per_side: float = 0.0
    tick_value_usd: float = MNQ_TICK_VALUE_USD

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ValueError("Execution model requires an identity")
        if (
            not math.isfinite(self.slippage_ticks_per_side)
            or self.slippage_ticks_per_side < 0
        ):
            raise ValueError("Slippage ticks per side must be finite and non-negative")
        if not math.isfinite(self.tick_value_usd) or self.tick_value_usd <= 0:
            raise ValueError("Tick value must be finite and positive")

    @property
    def slippage_usd_per_mnq_per_side(self) -> float:
        return self.slippage_ticks_per_side * self.tick_value_usd

    @property
    def slippage_usd_per_mnq_round_turn(self) -> float:
        return 2.0 * self.slippage_usd_per_mnq_per_side

    @property
    def is_frictionless(self) -> bool:
        return self.slippage_ticks_per_side == 0.0


FRICTIONLESS = ExecutionModel(model_id="perfect_linear_no_slippage_phase_1")
ONE_TICK_PER_SIDE = ExecutionModel(
    model_id="one_tick_per_side_sensitivity",
    slippage_ticks_per_side=1.0,
)

KNOWN_EXECUTION_MODELS = {
    model.model_id: model for model in (FRICTIONLESS, ONE_TICK_PER_SIDE)
}


def execution_model(model_id: str) -> ExecutionModel:
    model = KNOWN_EXECUTION_MODELS.get(model_id)
    if model is None:
        raise ValueError(f"Unsupported execution model: {model_id}")
    return model
