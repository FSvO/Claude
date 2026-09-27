#!/usr/bin/env python3
"""Refine open regions of a Heilbronn part on this VM until every piece is PROVED ("split until proved").

Usage (from any folder):
  python3 split_until_proved_260927.py --seeds open_leaves.json --under '<prefix JSON of the part>' --out DIR
         [--piece-secs 60] [--long-secs 300] [--near 1.02] [--heil /home/user/heil]

It only calls heil_tri.py with the same arguments run_parts.sh uses (no change to the mathematics):
  * seeds: the UNRESOLVED boundary regions in the combiner's open_leaves.json whose region contains every
    [triangle, sign] of --under (for example part 31's five signs);
  * a region is split on the first 4 candidate triangles not yet fixed (same default candidate list as
    combine_plan_260927.py) and its 16 pieces run for --piece-secs each; unresolved pieces become new regions;
  * a region whose best bound is within --near x target first gets one run of --long-secs on its own
    (prefix = region, split [], part 0) before it is split;
  * regions are processed lowest bound first; results go to DIR/<node>/result_boundary_<p>.json (+ log_<p>.txt, node.json);
  * a region with every orientation fixed gets one run of --leaf-secs; if that fails it is reported as left open
    (the driver then does not claim that everything was proved);
  * create DIR/STOP to stop after the current solver run; re-running the script resumes (existing results are reused).
Split and prefix strings are written in compact JSON (no spaces), like every other run in this project.
"""
import argparse, hashlib, heapq, itertools, json, os, subprocess, sys, time

T = 0.027426211734693878
N = 9
CAND = ([[0,3,4],[0,3,5],[1,2,4],[1,2,5],[0,3,6],[0,3,7],[1,2,6],[1,2,7],[0,3,8],[1,2,8],[0,2,4],[0,2,5],[1,3,4],[1,3,5],
         [0,2,6],[0,2,7],[1,3,6],[1,3,7],[0,2,8],[1,3,8]] + [list(t) for t in itertools.combinations(range(4, N), 3)])
CAND += [list(t) for t in itertools.combinations(range(N), 3) if list(t) not in CAND]   # every other triangle, e.g. (0,k,l)
TPLUS = {t for t in itertools.combinations(range(N), 3) if max(t) <= 3} | {(0, 1, k) for k in range(4, N)}


def compact(x):
    return json.dumps(x, separators=(',', ':'))


def canon(prefix):
    return compact(sorted([list(t), int(s)] for t, s in prefix))


def choose_split(region, size=4):
    fixed = {tuple(t) for t, s in region}
    return [c for c in CAND if tuple(c) not in fixed and tuple(c) not in TPLUS][:size]


def log(out, msg):
    line = time.strftime('%H:%M:%S UTC ', time.gmtime()) + msg
    print(line, flush=True)
    with open(os.path.join(out, 'progress.log'), 'a') as f:
        f.write(line + '\n')


def solve(heil, out, region, split, part, secs):
    """One heil_tri.py run; returns its result dict (reused if it already exists)."""
    node = hashlib.sha1((canon(region) + '|' + compact(split) + '|' + str(secs)).encode()).hexdigest()[:10]
    d = os.path.join(out, node)
    os.makedirs(d, exist_ok=True)
    meta = os.path.join(d, 'node.json')
    if not os.path.exists(meta):
        json.dump({'prefix': region, 'split': split, 'secs': secs}, open(meta, 'w'))
    res = os.path.join(d, f'result_boundary_{part}.json')
    if not os.path.exists(res):
        cmd = ['python3', 'heil_tri.py', '--n', str(N), '--case', 'boundary', '--cutoff', repr(T),
               '--split', compact(split), '--part', str(part), '--prefix', compact(region),
               '--threads', str(os.cpu_count()), '--timelimit', str(secs), '--out', os.path.abspath(res)]
        with open(os.path.join(d, f'log_{part}.txt'), 'w') as lf:
            subprocess.run(cmd, cwd=heil, stdout=lf, stderr=subprocess.STDOUT)
    return json.load(open(res))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', required=True)
    ap.add_argument('--under', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--piece-secs', type=int, default=60)
    ap.add_argument('--long-secs', type=int, default=300)
    ap.add_argument('--near', type=float, default=1.02)
    ap.add_argument('--leaf-secs', type=int, default=1800, help='time for a region with every orientation fixed')
    ap.add_argument('--heil', default='/home/user/heil')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    under = {(tuple(t), int(s)) for t, s in json.loads(a.under)}
    heap, count = [], itertools.count()
    for leaf in json.load(open(a.seeds)):
        region = [[list(t), int(s)] for t, s in leaf['region']]
        if leaf['case'] == 'boundary' and leaf['reason'] == 'UNRESOLVED' and under <= {(tuple(t), s) for t, s in region}:
            b = leaf.get('best_bound') or 1.0
            heapq.heappush(heap, (b / T, next(count), region, leaf.get('split') == [] and (leaf.get('runtime') or 0) >= a.long_secs))
    log(a.out, f'start: {len(heap)} seed region(s) under {a.under}')
    proved = runs = 0
    left_open = []          # regions that could not be split and were not proved: reported at the end
    while heap:
        if os.path.exists(os.path.join(a.out, 'STOP')):
            log(a.out, f'STOP file found: {len(heap)} region(s) still open; re-run to resume')
            return 1
        ratio, _, region, long_tried = heapq.heappop(heap)
        if ratio <= a.near and not long_tried:
            r = solve(a.heil, a.out, region, [], 0, a.long_secs); runs += 1
            if r.get('verdict') == 'PROVED':
                proved += 1; log(a.out, f'region PROVED by a {a.long_secs} s run ({r["runtime"]:.0f} s); open {len(heap)}'); continue
            if r.get('verdict') == 'BETTER_CONFIGURATION_FOUND':
                log(a.out, 'BETTER_CONFIGURATION_FOUND - stopping; verify with verify_config.py'); return 3
            heapq.heappush(heap, ((r.get('objbound') or T * 9) / T, next(count), region, True))
            continue
        split = choose_split(region)
        if not split:   # every orientation is fixed: give the region one long run on its own
            r = solve(a.heil, a.out, region, [], 0, a.leaf_secs); runs += 1
            if r.get('verdict') == 'PROVED':
                proved += 1; log(a.out, f'fully fixed region PROVED ({r["runtime"]:.0f} s); open {len(heap)}'); continue
            if r.get('verdict') == 'BETTER_CONFIGURATION_FOUND':
                log(a.out, 'BETTER_CONFIGURATION_FOUND - stopping; verify with verify_config.py'); return 3
            left_open.append(region)
            log(a.out, f'fully fixed region NOT proved in {a.leaf_secs} s (bound/target {(r.get("objbound") or 0) / T:.4f}); '
                       f'left open: {canon(region)}'); continue
        opened = 0
        for p in range(2 ** len(split)):
            if os.path.exists(os.path.join(a.out, 'STOP')):
                heapq.heappush(heap, (ratio, next(count), region, long_tried))
                log(a.out, f'STOP file found mid-region; it will be redone on resume (finished pieces are reused)')
                return 1
            r = solve(a.heil, a.out, region, split, p, a.piece_secs); runs += 1
            v = r.get('verdict')
            if v == 'PROVED':
                proved += 1
            elif v == 'BETTER_CONFIGURATION_FOUND':
                log(a.out, 'BETTER_CONFIGURATION_FOUND - stopping; verify with verify_config.py'); return 3
            else:
                child = region + [[t, (p >> i) & 1] for i, t in enumerate(split)]
                heapq.heappush(heap, ((r.get('objbound') or T * 9) / T, next(count), child, False)); opened += 1
        log(a.out, f'split region (bound/target {ratio:.3f}) on {compact(split)}: {2 ** len(split) - opened} pieces proved, '
                   f'{opened} open; total runs {runs}, proved {proved}, open regions {len(heap)}')
    if left_open:
        log(a.out, f'FINISHED WITH {len(left_open)} REGION(S) LEFT OPEN (see above): runs {runs}, proved {proved}')
        return 1
    log(a.out, f'ALL REGIONS PROVED by this driver: runs {runs}, proved {proved} '
               '(the certificate itself must still be checked with summarize.py and combine_plan_260927.py)')
    open(os.path.join(a.out, 'ALL_PROVED'), 'w').write('ok\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
