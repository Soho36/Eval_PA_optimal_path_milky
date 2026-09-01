# Architecture

The intended pipeline is:

1. verify the frozen RR1 import and timezone contract;
2. select the global one-position opportunity stream;
3. simulate each Evaluation independently from its activation time;
4. activate new PAs after successful Evaluations and fees;
5. for every accepted PA opportunity, enumerate all active PAs eligible at that
   entry timestamp;
6. apply one account-level copy to every eligible PA using that PA's contract
   count and state;
7. evaluate death and payout state separately for each PA;
8. process treasury, Evaluation purchases and PA replacements; and
9. emit cohort-level economics plus account-level exposure and correlation
   diagnostics.

The PA event must report both the global opportunity count and the number of
account-level copies. Unlike staggering, there is no capacity fill rate: an
eligible active PA either receives its copy or a recorded compliance rule blocks
it.

Files under `reference/shared_source/` are not imported by the active package.
This prevents accidental reuse of the parent router or inventory simulator.
