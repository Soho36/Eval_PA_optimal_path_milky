# Instructions for AI-assisted work

Before doing project work, read
`project_memory/BEGINNING_OF_A_WORK_SESSION.md` and follow its complete reading
order. Treat code, tests, manifests and generated results as stronger evidence
than project memory.

This repository is a completed-trade economic simulator for a Legacy 25K
Evaluation -> Legacy 25K PA -> withdrawal/reinvestment lifecycle. Its defining
PA-book behavior is copy-to-all: every accepted global strategy opportunity is
copied to every eligible active PA. It does not stagger signals, choose one PA,
or maintain dormant PA reserves.

Do not modify upstream repositories. Every imported artifact must retain its
source repository, Git revision and byte hash. The effective-dated rules in
`rules/` are primary inputs. Stop affected modeling work when a rule is missing,
ambiguous, or conflicts with the implementation.

Do not inherit conclusions from the parent staggering study. In particular,
`max_headroom`, K=2/S=1, dormant reserves, fill-rate congestion, and its policy
rankings are out of scope unless independently reintroduced and tested here.

Do not begin an integrated parameter sweep until the copy-to-all contract,
scaling rules, account activation timing, replacement policy and parity
fixtures are executable tests.
