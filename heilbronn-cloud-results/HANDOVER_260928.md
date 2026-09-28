# Handover: Heilbronn n = 9 coordinator, to a session with full access to FSvOAI/Claude (28 Sep 2026)

Full path: `heilbronn-cloud-results/HANDOVER_260928.md` in the public repository FSvO/Claude, branch `cloud-results`.

## Acronyms and abbreviations

| Term | Meaning |
|---|---|
| API | Application Programming Interface (GitHub's, for runs, job logs and artifacts) |
| UTC | Coordinated Universal Time |
| VM | Virtual Machine (a cloud session's 4-core computer) |

## Why a new session

- The previous session was attached to FSvO/Claude and could only read FSvOAI/Claude anonymously (git branches only), with no Actions API, no job logs and no artifacts. A second repository also named "Claude" cannot be attached to the same session.
- n = 9 GitHub run 36334867345 (started about 18:34 UTC on 27 Sep) finished with a green tick, but its results never reached the `results` branch (still only `run-1-n8`). Its save step most likely reports success even after every push fails; soundness review finding F6 in `soundness_review_260927.md` flagged exactly this.

## First tasks for the new session (attached to FSvOAI/Claude)

1. Read the original task prompt (`CLOUD_SESSION_PROMPT.md` in FSvOAI/Claude) and its rules: never change the mathematics in `heil_tri.py` or the target; no force-push or deleting branches or results; ask before anything that costs money or changes repository settings.
2. Clone this public repository read-only for the state and the tools: `git clone -b cloud-results https://github.com/FSvO/Claude.git fsvo-claude`. Read `heilbronn-cloud-results/STATUS_260927.md`, `STATUS_260928.md` and `soundness_review_260927.md`.
3. Get run 36334867345's results with the GitHub API: the `summary` artifact holds `summary.md` and every `result_*.json`. Check them:
   - 33 files (32 boundary parts plus the corners case);
   - n = 9, cutoff 0.027426211734693878, split `[[2,3,4],[2,3,5],[2,3,6],[2,3,7],[2,3,8]]`;
   - no BETTER_CONFIGURATION_FOUND (verify any with `verify_config.py`).

   If the user has uploaded `summary.zip` to FSvO/Claude `main` in the meantime, that is the same data.
4. Read the job log of the run's "summary" job, step "Save results to the 'results' branch", and find why the push failed. Fix the step so a failed push fails the job, and so a first-ever/orphan run retries correctly (review finding F6). Only workflow plumbing may change; no mathematics.
5. Combine all n = 9 results with `tools/combine_plan_260927.py`:
   - roots: the GitHub run folder plus the VM folders from `heilbronn-cloud-results/`, i.e. `corners9_probe`, `cantrell_leaf31`, `probe9_p31`, `split31_A/B/C`, `s31A_c*` and `cc31`;
   - skip `sanity7` and `negctl7` (n = 7).

   "Certified" may be said only if `summarize.py` over the complete n = 9 set prints CERTIFIED and the combiner's independent check agrees, with no BETTER suspect.
6. Spot check (task step 4): re-run two parts GitHub reports as PROVED, with the identical split text and hours = 5.5 (`run_parts.sh`), and confirm the verdict.
7. Refinement (task step 5) of every UNRESOLVED part:
   - Use split A style first: `[[0,3,4],[0,3,5],[1,2,4],[1,2,5]]`, then the combiner's default candidate list.
   - Short time limits per piece worked best (60 s pieces, with 300 s runs for pieces within 2% of the target).
   - The new session may start runs itself with the GitHub Actions tools, if the user agrees.
   - The batch workflow `tools/heilbronn-batch_260927.yml` (tested) runs many regions per dispatch. Adding it to FSvOAI/Claude is the user's decision.

## State at 08:30 UTC, 28 Sep 2026

- n = 7 sanity check: CERTIFIED. n = 7 negative control (target below the optimum): correctly not certified.
- n = 8 validation (GitHub run 1): CERTIFIED, 17 of 17, 2.54 h solver time.
- n = 9 corners case: PROVED on the VM (466 s).
- Cantrell's configuration lies in parts 0, 29, 30 and 31 (one embedding each). Part 31 refinement on the old VM, driver `tools/split_until_proved_260927.py` (results in `cc31/`, progress log `cc31/progress.log`):
  - 4,104 VM n = 9 runs, 3,729 PROVED, 14.7 h solver time;
  - 53 regions of part 31 open (bound/target 1.005 to 3.43, median 1.42), plus 7 queued pieces.
- To resume that driver on a new VM:
  - copy `heilbronn-cloud-results/cc31` to `<heil clone>/results/cloud/cc31`, and the other n = 9 folders to `results/cloud/`;
  - run the combiner to get `open_leaves.json`;
  - start the driver with `--under '[[[2,3,4],1],[[2,3,5],1],[[2,3,6],1],[[2,3,7],1],[[2,3,8],1]]'`;
  - put `gurobi.env` (`NodefileStart 6`) in the heil clone first.
- Numerics: the solver's value can exceed the exact value of its own points by up to 1.8×10⁻⁶ on near-optimal 9-point sets. The gap trap happens if a part ends OPTIMAL with its bound above the target; for the parts holding Cantrell's set this becomes possible once the solver's value passes 0.0274248. It has not happened yet (0 OPTIMAL-but-unproved results). Tighter tolerances (FeasibilityTol and IntFeasTol 10⁻⁹ via `gurobi.env`) are an open decision for the user.
- Slide: https://claude.ai/artifact/4iyFpmzZDQmvUTsaYQwgUn (source in `slide_260928/`).
