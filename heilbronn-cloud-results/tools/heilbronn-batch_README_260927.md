# heilbronn-batch: many refinement jobs in one GitHub run

| Term | Meaning |
|---|---|
| JSON | JavaScript Object Notation: the plain-text format of the "nodes" input |
| YAML | The text format of GitHub workflow files |
| id | A 10-character code naming one region and its split; it appears in job and file names |

1. **Add the file (once):** on github.com open the repository FSvOAI/Claude, click "Add file" › "Create new file", type the name `.github/workflows/heilbronn-batch.yml`, paste in the whole of `heilbronn-batch_260927.yml`, and click "Commit changes" on the `main` branch.
2. **Start a batch:** Actions tab › "heilbronn-batch" (left list) › "Run workflow". Leave n, target, solver and runner as they are. Set hours (at most 5.5), paste the one-line "nodes" text Claude gives you, then click the green "Run workflow" button.
3. **What "nodes" is:** a list of unresolved regions, each written as its `prefix` (copied from a summary) plus the triangles to `split` it on. Every part of every split becomes one job: at most 256 jobs per run, and 20 run at the same time.
4. **Wrong inputs cost nothing:** the first job, "plan", checks everything within a minute. If something is wrong it turns red and says what to fix, and nothing is solved.
5. **While it runs:** the "plan" job page shows a table of the jobs. Each solver job is called "solve <id> part <p>". A red solve job means that job crashed; the other jobs still finish.
6. **Where results appear:** at the end, the "summary" job shows the summary on the run's page. It also saves every file to the branch `results`, in the folder `results/batch-<run number>-n<n>/` (for example `results/batch-2-n9/`).
7. **What the summary means:** "Not (yet) a complete certificate" is normal for a batch. Only Claude's check across all runs together can say CERTIFIED. Send Claude the run number when it finishes.
8. **Corners case:** this workflow never runs the corners-occupied case. That case still comes from `heilbronn-certify`.
