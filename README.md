# Legacy 25K copy-to-all study

A completed-trade economic simulator for a Legacy 25K Evaluation -> PA ->
withdrawal lifecycle. Its defining behavior is **copy-to-all**: every accepted
global opportunity is copied to every eligible active PA. No staggering, no
routing competition, no dormant reserves.

The study asks whether a synchronized book of 1-20 PAs can be grown and
harvested economically, and exists to be differenced against the parent
staggering study.

## Read in this order

1. `STATUS.md` — where the work stands and what blocks a citable result.
2. `ASSUMPTIONS.md` — why the model is shaped this way, and its known limits.
3. `config/runtime.json` — every value the simulator reads.

## Run

```powershell
.\scripts\run_tests.ps1
.\venv\Scripts\python.exe scripts\run_sweep.py --n 1 3 --workers 4 --exploratory
```

While `config/runtime.json` lists blockers, a run must pass `--exploratory` and
its manifest is labelled accordingly. Do not report an exploratory run as a
study result.

## Layout

- `src/milky_cow/` — the simulator.
- `tests/` — behavioural and economic tests, plus defect regressions.
- `results/` — run manifests. Each seals its own outputs by hash.
- `manifests/`, `rules/` — frozen, hash-verified inputs. Do not edit.
- `reference/` — read-only parent snapshots used for parity checks.
- `archive/` — transfer paperwork, superseded configs and prior project
  memory. Evidence, not mandatory reading.
