# Soundness review of the Heilbronn certification pipeline (27 Sep 2026)

Full path on the cloud VM: `/home/user/Claude/heilbronn-cloud-results/soundness_review_260927.md`, in the repository FSvO/Claude, branch `cloud-results`.
The raw output of the review (all findings, evidence and verifier verdicts) is in `soundness_review_raw_260927.json` in the same folder.

## Acronyms and abbreviations

| Term | Meaning |
|---|---|
| BETTER | The verdict BETTER_CONFIGURATION_FOUND: the solver's points, recomputed, have minimum area above the target |
| CI | Continuous Integration (GitHub Actions) |
| JSON | JavaScript Object Notation (format of the result files) |
| LP | Linear Program |
| OOM | Out Of Memory (the operating system kills the process) |
| QCP | Quadratically Constrained Program |
| T | The unit right triangle {x ≥ 0, y ≥ 0, x + y ≤ 1} |
| VM | Virtual Machine (this cloud session's 4-core computer) |
| zub | Upper bound on the variable z (minimum area) in `heil_tri.py`; default 0.5 |

## How the review was done

- Four independent reviewers covered four areas:
  - the geometry of the model in `heil_tri.py`;
  - solver tolerances and the verdict logic;
  - the completeness check in `summarize.py`;
  - the GitHub workflow and `run_parts.sh`.
- An adversarial verifier re-derived each reviewer's findings and tried to refute them. A final critic then looked for anything left unchecked. That is 9 agents in total.
- The reviewers did not run the solver, and nothing in the repository was changed. Evidence consists of exact rational arithmetic, synthetic result files fed to `summarize.py`, and the solver logs already on disk.
- arxiv.org is blocked by this session's network policy, so the paper arXiv:2607.15021 could not be read.
- I checked the most important claims myself, as noted below.

## Bottom line

- Nothing found would make a CERTIFIED printed for the current n = 9 run false. The two soundness holes found are latent: the n = 9 run as specified (no `--zub`, corners case not split) never triggers them.
- The model is exact for its case:
  - Every feasible point is a real configuration in T.
  - Every configuration of the assumed structure is feasible in some part, at its true minimum area.
- The structural case split (all three corners occupied, or two points on one side and one on each other side) has an elementary proof that does not need the paper (details below). A mathematician should confirm this before publication.
- The main practical risks:
  - running out of memory on long jobs, now addressed with `gurobi.env`;
  - solver round-off in the four parts that contain Cantrell's configuration;
  - mistakes when combining results from several runs.

## Checked and correct

| Item | Result |
|---|---|
| Signed-area formula through the products w = x·y | Equals half the determinant for all 84 triangles in both cases (symbolic expansion and 2000 exact random tests) |
| Orientation constraints z ≤ e + (1 − b), z ≤ −e + b | Valid, because every triangle in T has area at most ½ and z ≤ ½ |
| Always-positive triangles in the boundary case (among p0–p3, and (p0, p1, k)) | Forced by geometry; they are not extra assumptions. For example, 2A(1,2,3) = y3(1 − y2 − x1) + x1·y2 ≥ 0 on the unit cube |
| Orientation signs in the corners case | Forced: 2A(0,1,k) = y_k, 2A(0,2,k) = −x_k, 2A(1,2,k) = 1 − x_k − y_k |
| Symmetry reductions (x0 ≤ x1, x0 + x1 ≤ 1, free points sorted by x, then split signs read off) | Jointly valid; checked on 5157 random exact configurations, which hit all 32 parts |
| Cantrell's configuration | Minimum area exactly 43/1568. It lies in parts 0, 29, 30 and 31, one distinct embedding in each; the configuration has a 3-fold affine symmetry (x, y) → (y, 1 − x − y) (checked exactly), so it appears 3 times per part |
| n = 7 negative control (my run, target 7/144 × (1 − 10⁻⁴), below the optimum) | Parts 0, 5, 6 and 7 report BETTER, and `summarize.py` does NOT certify. `verify_config.py` on the raw solver points gives 0.0486107; rounded to denominators ≤ 100 they give exactly 7/144. The safeguard chain works |
| Cantrell's leaf in part 31, every orientation fixed (my run) | PROVED in 1.2 s (bound 0.0274257 ≤ target). The unavoidable leaf around the optimum is cheap to close |

### The case split does not need Proposition 1 (reviewer's argument; key steps re-checked by me)

- **Lemma 1.** Suppose all points on the bottom edge have x < ½ (or the bottom edge is empty). Then the affine map f(x, y) = (x, y) + ε·(M(x, y) + t), with M = [[½ + η, 0], [−1, −½ + η]] and t = (0, ½ − η), behaves as follows:
  - it fixes the corner (0, 1);
  - it maps the left edge and the hypotenuse into themselves;
  - it keeps every point inside T;
  - its determinant is 1 + 2ηε + ε²(η² − ¼) > 1 for small ε.

  So every triangle area grows, which contradicts optimality. Combined with the symmetries of T, this means every side of an optimal configuration has points on both sides of its midpoint.
- **Lemma 2.** If the only boundary points are the three midpoints, the rotation-scaling about (½, ½) with linear part [[1, −2s], [2s, 1]] has determinant 1 + 4s² > 1, again a contradiction.
- **Enumeration.** Two independent enumerations (46,656 patterns, and all 2¹⁸ subsets of 18 exact candidate points) show that every other allowed pattern is (a), all corners occupied, or (b), two distinct points on one side plus a distinct point on each of the other two sides.

## Findings (all confirmed by the adversarial verifier unless stated)

| # | Severity | Finding | Effect on the n = 9 work | What we do |
|---|---|---|---|---|
| 1 | Critical if triggered; latent now | `summarize.py` line 71 accepts ANY PROVED corners result with an empty prefix, even one part of a split corners run (I confirmed this by reading the line) | None while the corners case runs unsplit, as in the planned n = 9 run | If the corners case ever needs splitting, check its coverage separately; never rely on `summarize.py` alone for it |
| 2 | Low/medium, latent | `--zub` is never checked; a value below the target would give a false PROVED | None: no runner passes `--zub` (all results so far have zub = 0.5) | Check zub = 0.5 in every result before claiming anything |
| 3 | Medium (numerics) | With Gurobi's default tolerances the solver's best value can exceed the true value of its points (theoretical worst case about 3.3×10⁻⁶ near Cantrell's configuration, above the n = 9 margin of 2.74×10⁻⁶). If the best value exceeds 0.0274248 (= target / (1 + 5×10⁻⁵)), a part can end OPTIMAL with its bound still above the target and stay UNRESOLVED however far it is split | Only the parts containing Cantrell's configuration. Observed excess: at most 7.9×10⁻⁷ (n = 7), 5.5×10⁻⁷ (n = 8, GitHub run #1) and 4.7×10⁻⁷ (Cantrell's leaf above) | Watch the best value of parts 0, 29, 30 and 31. If one exceeds 0.0274248, tighten FeasibilityTol and IntFeasTol to 10⁻⁹ through `gurobi.env` for that part's refinement (a solver setting, not mathematics; your decision). MIPGap cannot be changed through `gurobi.env` because `heil_tri.py` sets it |
| 4 | Medium (operational) | About 1 KB of memory per open node; a 5.5-hour job could approach the 16 GB of a GitHub runner, and a job killed for lack of memory writes no result | Any long n = 9 job | Addressed: `gurobi.env` with `NodefileStart 6` (on the VM now; needs adding to FSvOAI/Claude) |
| 5 | Medium | If the same part appears twice (for example GitHub PROVED and a VM re-run UNRESOLVED), the file that sorts last wins, so a PROVED result can be hidden. This errs on the safe side | Combining GitHub and VM results | Spot checks use the same time limit, and duplicates are handled explicitly when combining |
| 6 | Medium | Split lists are compared as raw text: the same split typed with different spaces does not combine | Refinements run partly on GitHub and partly on the VM | Always use exactly the same split text (no spaces) on GitHub and on the VM |
| 7 | Medium | The `results` branch mixes n = 8 and n = 9, so `summarize.py results` never prints CERTIFIED | Final check | Summarise a folder that holds only n = 9 results |
| 8 | Medium | The corners case has no refinement route (its printed advice points to a boundary rerun) | Only if the n = 9 corners case is UNRESOLVED | Would need a custom split and a manual coverage check (see finding 1) |
| 9 | Low | `python … \| tee` without pipefail hides solver crashes; a truncated result file makes `summarize.py` crash; the save-to-branch step can report success after failed pushes; results carry no code or solver version | Operational only; a missing part is never counted as proved | Check that the number of result files matches the number of parts |
| 10 | Info | The README says the certificate depends on Proposition 1; the elementary argument above removes that dependence | Documentation | Optional README note |

## Corrections to my earlier statements

- Cantrell's configuration has one distinct embedding in each of parts 0, 29, 30 and 31, not three. My script counted the same labelled configuration three times because of its 3-fold symmetry.
