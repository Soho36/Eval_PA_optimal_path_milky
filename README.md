# Legacy 25K milky-cow starter bundle

This is a temporary, self-contained handoff bundle. Move the whole directory to
its final location, initialize a new Git repository there, create its virtual
environment, and add that final folder to Codex as a new local project.

The study asks whether a synchronized book of 1-20 Legacy 25K PAs can be grown
and harvested economically when every eligible active PA receives the same
accepted global signal. It is intentionally separate from the R=1 account-
staggering/inventory study.

## After moving the directory

From its final directory in PowerShell. This is a new repository, so no branch
needs to be created in the parent staggering repository:

```powershell
git init -b main
& 'C:\Program Files\Python312\python.exe' -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe scripts\verify_transfer_manifest.py
.\scripts\run_tests.ps1
git add .
git commit -m "Initialize Legacy 25K milky-cow study"
```

If the system Python path differs, replace only the interpreter in the second
command. The project-local `.venv` is used thereafter.

## What is included

- the full frozen RR1 completed-trade tape and its import manifest;
- Legacy 25K Evaluation, PA and payout rules;
- the six payout-policy definitions as candidates;
- the pinned EODMAE Evaluation behavior fixture;
- exact parent/upstream provenance;
- read-only snapshots of potentially reusable parent modules and tests; and
- a minimal executable study-contract test.

Files under `reference/` are evidence and implementation references, not active
package code. Review and import them deliberately rather than copying the
parent simulator wholesale.

## What is deliberately excluded

- Account-staggering routing fixtures;
- the superseded `$200/$400` behavior lock;
- inventory-grid results and rankings;
- `max_headroom` routing; and
- dormant-PA inventory mechanics.

Read `project_memory/BEGINNING_OF_A_WORK_SESSION.md` before development.
Use `NEW_CHAT_PROMPT.md` as the first message in the new Codex local project.
