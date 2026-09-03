# Instructions for AI-assisted work

Read `STATUS.md` for where the work stands, then `ASSUMPTIONS.md` for why the
model is shaped the way it is. Both are prose and neither is loaded by code.
Every value the simulator reads is in `config/runtime.json`.

Treat code, tests and generated results as stronger evidence than prose. If
prose and a test disagree, the test wins and the prose is stale — fix it.

This repository is a completed-trade economic simulator for a Legacy 25K
Evaluation -> PA -> withdrawal lifecycle. Its defining behavior is copy-to-all:
every accepted global opportunity is copied to every eligible active PA. It
does not stagger signals, choose one PA, or hold dormant reserves.

Frozen inputs stay hash-verified: `manifests/rr1_import_20260829.json`,
`manifests/upstream_evidence_20260829.json`, the files in `rules/`, and the
Evaluation behavior-lock fixture. Do not edit them. Local source and prose are
governed by Git; every run records the revision, working-tree digest and a hash
of each output it writes.

Do not inherit conclusions from the parent staggering study. Adopting a
mechanic for comparability is deliberate and recorded in `ASSUMPTIONS.md`;
adopting a result is not.

`archive/` holds transfer paperwork, superseded configs and prior project
memory. It is evidence, not mandatory reading.

While `config/runtime.json` lists blockers before a citable sweep, any run must
pass `exploratory=True` and its manifest is labelled exploratory. Do not report
an exploratory run as a study result.
