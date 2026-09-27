#!/usr/bin/env python3
"""combine_plan_260927.py - combine Heilbronn certification results from several folders, check coverage
independently of summarize.py, and plan the next refinement runs.   (Python 3.11, standard library only)

Usage
  python3 combine_plan_260927.py --n 9 --target 0.027426211734693878 --roots DIR [DIR ...] --out OUTDIR
         [--summarize /home/user/heil/summarize.py] [--candidates JSON] [--split-size 4] [--hours H]
         [--label-prefix L]

  --roots         folders searched recursively for result_*.json (a checkout of the GitHub 'results' branch,
                  the VM's results/cloud, ...). The originals are only read, never changed.
  --out           a new or empty folder. It receives verbatim copies of the selected result files,
                  report.md, plan.json and summary_summarize.md (summarize.py's output over the copies).
  --summarize     path of summarize.py (default /home/user/heil/summarize.py); pass '' to skip it.
                  The VM commands in the plan are meant to be run in the folder that holds it.
  --candidates    JSON list of triangles, or the path of a file holding one, in the order they should be
                  used for new splits (default: DEFAULT_CANDIDATES below, then all triangles among 4..n-1).
  --split-size    triangles per proposed split (default 4, i.e. 16 parts per region).
  --hours         solver time limit per part in the proposed runs (default 5.5).
  --label-prefix  prefix of the VM result-folder labels in the proposed run_parts.sh commands
                  (default 'r<month><day><hour><minute><second>_', so labels do not reuse an old folder).

What it does (numbers match the sections of report.md)
  1. reads every result_*.json under the roots; an unreadable or truncated file is reported, never fatal;
  2. keeps the rows with this n and this target (exact float equality) and counts the others by reason;
  3. checks each kept row for proof use: zub >= 0.5, case boundary/vertices, verdict PROVED backed by the
     status or the bound, well-formed split and prefix (odd triangles only give warnings: heil_tri.py then
     solves a larger region, which is still sound);
  4. lists every BETTER_CONFIGURATION_FOUND row first (also rows whose points, recomputed here, beat
     their target) and always copies it;
  5. groups duplicate rows by canonical key (case, sorted prefix, split, part) and copies one file per key;
  6. reports split texts that differ only in spacing (summarize.py treats them as different splits);
  7. runs summarize.py over the copies;
  8. decides coverage of the boundary tree and of the corners (vertices) tree with its own code;
  9. lists the open leaves of both trees, and
 10. proposes the next runs: plan.json, the value for the batch workflow input 'nodes', classic workflow
     inputs, and VM commands.

Output layout
  OUTDIR/<index>_<origin>/result_*.json    verbatim copies: one file per canonical key (rows valid for proof)
                                           plus every BETTER row with this n and target. summarize.py runs
                                           over OUTDIR, so it sees exactly these files.
  OUTDIR/better_other/<index>_<origin>/BETTER_<name>  or  UNPARSED_<name>
                                           verbatim copies of BETTER rows for another n or target or with
                                           malformed fields, and of unparseable files that contain the text
                                           BETTER_CONFIGURATION_FOUND; renamed so summarize.py skips them.
  OUTDIR/report.md                         the report (also printed)
  OUTDIR/plan.json                         {"n","target","hours","nodes":[{"case","prefix","split","parts",
                                           "reason","best_bound","note"}]}
  OUTDIR/open_leaves.json                  every open leaf with its full region prefix
  OUTDIR/summary_summarize.md              written by summarize.py

Exit codes (the first that applies)
  3  a BETTER_CONFIGURATION_FOUND row with this n exists (any target; also an unparseable file that contains
     that text, unless it names another n): check it with verify_config.py first
  2  input problems: unreadable or truncated files, rows with missing or malformed fields, a missing root,
     bad arguments, or OUTDIR not empty
  0  CERTIFIED by this tool's own coverage check (boundary tree and corners tree fully covered)
  1  not certified: open regions remain (see the plan)
"""
import argparse
import datetime
import glob
import hashlib
import itertools
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter

BETTER = 'BETTER_CONFIGURATION_FOUND'
# Fields every kept row must have (heil_tri.py always writes them; summarize.py needs them).
REQUIRED = ('n', 'case', 'cutoff', 'zub', 'split', 'part', 'prefix', 'verdict', 'status', 'runtime')
MAX_SPLIT = 16          # longer splits (65536+ parts) are not used for proof, to keep the checks bounded
ZUB_MIN = 0.5           # heil_tri.py's model is a relaxation only if z may reach 1/2 (any area in T is <= 1/2)
# Mirror of the input checks of tools/heilbronn-batch_260927.yml (27 Sep 2026), used to decide which plan
# regions can go into the batch workflow: boundary case, split of 1..6 sorted triangles outside T+, prefix
# without repeats or T+ triangles, split not overlapping the prefix, at most 256 jobs per run.
BATCH_MAX_SPLIT = 6
BATCH_MAX_JOBS = 256
DEFAULT_CANDIDATES = [[0, 3, 4], [0, 3, 5], [1, 2, 4], [1, 2, 5], [0, 3, 6], [0, 3, 7], [1, 2, 6], [1, 2, 7],
                      [0, 3, 8], [1, 2, 8], [0, 2, 4], [0, 2, 5], [1, 3, 4], [1, 3, 5], [0, 2, 6], [0, 2, 7],
                      [1, 3, 6], [1, 3, 7], [0, 2, 8], [1, 3, 8]]


# ----------------------------------------------------------------------------------------------- helpers
def compact(obj):
    """Canonical JSON text: no spaces (the form the plan prints and compares)."""
    return json.dumps(obj, separators=(',', ':'))


def is_int(v):
    return type(v) is int          # excludes bool, which is a subclass of int


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def as_float(v):
    """float(v) for a real number, else None."""
    return float(v) if is_num(v) else None


def short(text, width=60):
    text = str(text)
    return text if len(text) <= width else text[:width - 1] + '…'


def ranges(nums):
    """[0,1,2,5,7,8] -> '0-2, 5, 7-8' (for readable part lists)."""
    nums, out, i = sorted(nums), [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f'{nums[i]}-{nums[j]}')
        i = j + 1
    return ', '.join(out)


def forced_triangles(case, n):
    """Triangles whose sign heil_tri.py fixes itself: T+ (and T- for the corners case), copied from build()."""
    if case == 'boundary':
        return ({t for t in itertools.combinations(range(n), 3) if max(t) <= 3}
                | {(0, 1, k) for k in range(4, n)})
    return ({(0, 1, 2)} | {(0, 1, k) for k in range(3, n)} | {(1, 2, k) for k in range(3, n)}
            | {(0, 2, k) for k in range(3, n)})


def recompute_min_area(points, n):
    """Minimum triangle area of a row's points, computed exactly as heil_tri.py does (clip into T first).
    Returns None when the points are missing or malformed."""
    if not isinstance(points, list) or len(points) != n or n < 3:
        return None
    pts = []
    for p in points:
        if not (isinstance(p, list) and len(p) == 2 and all(is_num(c) and math.isfinite(c) for c in p)):
            return None
        px, py = max(float(p[0]), 0.0), max(float(p[1]), 0.0)
        if px + py > 1:
            s = px + py
            px, py = px / s, py / s
        pts.append((px, py))
    return min(abs((q[0] - p[0]) * (r[1] - p[1]) - (r[0] - p[0]) * (q[1] - p[1])) / 2
               for p, q, r in itertools.combinations(pts, 3))


def parse_split(text):
    """Split text -> list of triangles (each a list of 3 ints), or raise ValueError."""
    v = json.loads(text)
    if not isinstance(v, list) or not all(isinstance(t, list) and len(t) == 3 and all(is_int(i) for i in t)
                                          for t in v):
        raise ValueError('split must be a JSON list of [i,j,k] integer triples')
    return v


def parse_prefix(text):
    """Prefix text -> list of [[i,j,k], sign] entries, or raise ValueError."""
    v = json.loads(text)
    ok = isinstance(v, list) and all(
        isinstance(e, list) and len(e) == 2 and isinstance(e[0], list) and len(e[0]) == 3
        and all(is_int(i) for i in e[0]) and is_int(e[1]) for e in v)
    if not ok:
        raise ValueError('prefix must be a JSON list of [[i,j,k], sign] entries with integers')
    return v


def triangle_warnings(split, prefix, n, case):
    """Oddities that heil_tri.py tolerates by solving a LARGER region than intended (still sound):
    unsorted / repeated / out-of-range triples are never matched, signs other than 0/1 leave the triangle
    free, T+/T- triangles keep their forced sign, and a split bit overrides the prefix sign."""
    out = []
    bad = lambda t: not (0 <= t[0] < t[1] < t[2] < n)
    forced = forced_triangles(case, n)
    for t in split:
        if bad(t):
            out.append(f'split triangle {t} is not a sorted triple of distinct points 0..{n - 1} (heil_tri.py ignores it)')
        elif tuple(t) in forced:
            out.append(f'split triangle {t} has a sign forced by the {case} case (heil_tri.py ignores the split bit)')
    if len({tuple(t) for t in split}) != len(split):
        out.append('split repeats a triangle (the later bit wins in heil_tri.py)')
    for t, s in prefix:
        if bad(t):
            out.append(f'prefix triangle {t} is not a sorted triple of distinct points 0..{n - 1} (heil_tri.py ignores it)')
        elif tuple(t) in forced:
            out.append(f'prefix triangle {t} has a sign forced by the {case} case (heil_tri.py ignores the prefix sign)')
        if s not in (0, 1):
            out.append(f'prefix sign {s} for {t} is not 0 or 1 (heil_tri.py leaves that triangle free)')
    if len({tuple(t) for t, _ in prefix}) != len(prefix):
        out.append('prefix fixes a triangle more than once (the last entry wins in heil_tri.py)')
    both = sorted({tuple(t) for t in split} & {tuple(t) for t, _ in prefix})
    if both:
        out.append(f'split triangles {[list(t) for t in both]} are also in the prefix (the split bit wins in heil_tri.py)')
    return out


# ----------------------------------------------------------------------------------------------- rows
class Row:
    """One parsed result file and everything this tool finds out about it."""

    def __init__(self, root, path, raw, data):
        self.root, self.path, self.raw, self.data = root, path, raw, data
        self.sha = hashlib.sha256(raw).hexdigest()
        self.category = None        # 'kept', 'other_n', 'other_target' or 'broken'
        self.problems = []          # input problems (exit code 2); the row is not used for proof
        self.rejects = []           # reasons the row cannot count for proof (still reported)
        self.warnings = []          # oddities that do not stop the row from counting
        self.key = None             # canonical key (case, prefix, split, part) when it can be computed
        self.prefix_list = self.split_list = None
        self.better_why = []        # why this row is treated as BETTER
        self.recomputed = None      # this tool's recomputation of the minimum area of the points
        self.copied_to = None

    def get(self, k, default=None):
        return self.data.get(k, default)

    @property
    def verdict(self):
        return self.data.get('verdict')

    @property
    def valid(self):
        """True if the row may be used in the coverage proof."""
        return self.category == 'kept' and self.key is not None and not self.problems and not self.rejects

    @property
    def objbound(self):
        return as_float(self.data.get('objbound'))


def examine(row, n_wanted, target):
    """Sort a parsed row into a category and fill in its problems, rejections, warnings and key."""
    d = row.data
    n, cutoff = d.get('n'), as_float(d.get('cutoff'))
    # BETTER: by verdict, or by recomputing the points against the row's own cutoff.
    if is_int(n):
        row.recomputed = recompute_min_area(d.get('points'), n)
    if row.verdict == BETTER:
        row.better_why.append('verdict BETTER_CONFIGURATION_FOUND')
    if row.recomputed is not None and cutoff is not None and row.recomputed > cutoff and row.verdict != BETTER:
        row.better_why.append(f'recomputed minimum area {row.recomputed!r} of its points exceeds its cutoff '
                              f'{cutoff!r}, but its verdict is {row.verdict}')
    # 2. keep only this n and this target
    if not is_int(n) or cutoff is None:
        row.category = 'broken'
        row.problems.append('field n or cutoff is missing or not a number')
        return
    if n != n_wanted:
        row.category = 'other_n'
        return
    if cutoff != target:
        row.category = 'other_target'
        return
    row.category = 'kept'
    # 3. structure (input problems) ...
    missing = [k for k in REQUIRED if k not in d]
    if missing:
        row.problems.append(f'missing fields {missing}')
    types = [('case', str), ('split', str), ('prefix', str), ('status', str)]
    for k, typ in types:
        if k in d and not isinstance(d[k], typ):
            row.problems.append(f'field {k} is not a {typ.__name__}')
    if 'part' in d and not is_int(d['part']):
        row.problems.append('field part is not an integer')
    if 'runtime' in d and not is_num(d['runtime']):
        row.problems.append('field runtime is not a number')
    if 'verdict' in d and not isinstance(d['verdict'], (str, type(None))):
        row.problems.append('field verdict is not a string')
    if isinstance(d.get('split'), str):
        try:
            row.split_list = parse_split(d['split'])
        except ValueError as e:
            row.problems.append(f'malformed split {short(d["split"], 80)!r}: {e}')
    if isinstance(d.get('prefix'), str):
        try:
            row.prefix_list = sorted(parse_prefix(d['prefix']))
        except (ValueError, TypeError) as e:
            row.problems.append(f'malformed prefix {short(d["prefix"], 80)!r}: {e}')
    if row.problems:
        return
    # ... then proof validity (row still reported either way)
    zub = as_float(d['zub'])
    if zub is None or zub < ZUB_MIN:
        row.rejects.append(f'zub = {d["zub"]!r} < {ZUB_MIN}: the model is then not a relaxation, so PROVED means nothing')
    if d['case'] not in ('boundary', 'vertices'):
        row.rejects.append(f"case {d['case']!r} is neither 'boundary' nor 'vertices'")
    d_split = len(row.split_list)
    if d_split > MAX_SPLIT:
        row.rejects.append(f'split has {d_split} triangles (more than {MAX_SPLIT}); not used by this checker')
    elif not 0 <= d['part'] < 2 ** d_split:
        row.rejects.append(f"part {d['part']} is outside 0..{2 ** d_split - 1} for this split")
    if row.verdict == 'PROVED':
        ob = row.objbound
        if not (d['status'] in ('INFEASIBLE', 'CUTOFF') or (ob is not None and ob <= cutoff)):
            row.rejects.append(f"verdict PROVED is not backed by status {d['status']!r} and bound {d.get('objbound')!r}")
    if row.better_why and row.verdict == 'PROVED':
        row.rejects.append('its points beat the target, so PROVED cannot be right')
    if d['case'] in ('boundary', 'vertices'):
        row.warnings += triangle_warnings(row.split_list, row.prefix_list, n, d['case'])
    row.key = (d['case'], compact(row.prefix_list), compact(row.split_list), d['part'])


# ----------------------------------------------------------------------------------------------- tree
class Tree:
    """Split tree of one case, built from the rows that are valid for proof.
    A node is a region identified by its canonical prefix; refining it with split S creates 2^|S| children
    whose prefixes are the node prefix plus [[S[i], (k >> i) & 1]]."""

    def __init__(self, case, rows):
        self.case = case
        self.nodes = {}          # prefix key -> {split key: {part: [rows]}}
        self.prefix_of = {}      # prefix key -> sorted prefix list
        self.split_of = {}       # split key -> split list (order kept)
        for r in rows:
            c, pkey, skey, part = r.key
            self.nodes.setdefault(pkey, {}).setdefault(skey, {}).setdefault(part, []).append(r)
            self.prefix_of[pkey] = r.prefix_list
            self.split_of[skey] = r.split_list
        self.memo = {}

    def rows(self, pkey, skey, k):
        return self.nodes.get(pkey, {}).get(skey, {}).get(k, [])

    def proved(self, pkey, skey, k):
        return any(r.verdict == 'PROVED' for r in self.rows(pkey, skey, k))

    @staticmethod
    def child(plist, slist, k):
        clist = sorted(plist + [[t, (k >> i) & 1] for i, t in enumerate(slist)])
        return compact(clist), clist

    def covered(self, pkey, plist):
        """A node is covered iff for SOME split with rows here, every part is PROVED or its child is covered."""
        if pkey in self.memo:
            return self.memo[pkey]
        self.memo[pkey] = False     # guard; only an empty split could lead back here, and that is skipped below
        result = False
        for skey in sorted(self.nodes.get(pkey, {})):
            slist = self.split_of[skey]
            if all(self.part_done(pkey, plist, skey, slist, k) for k in range(2 ** len(slist))):
                result = True
                break
        self.memo[pkey] = result
        return result

    def part_done(self, pkey, plist, skey, slist, k):
        if self.proved(pkey, skey, k):
            return True
        ckey, clist = self.child(plist, slist, k)
        return ckey != pkey and self.covered(ckey, clist)

    def best_split(self, pkey):
        """The split followed when listing open leaves: most PROVED parts, then most rows, then text order."""
        def score(skey):
            d = len(self.split_of[skey])
            proved = sum(1 for k in range(2 ** d) if self.proved(pkey, skey, k))
            rows = sum(len(v) for v in self.nodes[pkey][skey].values())
            return (-proved, -rows, skey)
        return min(self.nodes[pkey], key=score)

    def open_leaves(self):
        """Depth-first list of the uncovered leaves under the root prefix []."""
        leaves, seen = [], set()

        def visit(pkey, plist, depth):
            if pkey in seen or self.covered(pkey, plist):
                return
            seen.add(pkey)
            if pkey not in self.nodes:          # only possible at the root: nothing was ever run here
                leaves.append(dict(case=self.case, parent=plist, split=None, part=None, region=plist,
                                   reason='MISSING', detail='no result at all for this case', best=None,
                                   runtime=None, file=None, depth=depth))
                return
            skey = self.best_split(pkey)
            slist = self.split_of[skey]
            for k in range(2 ** len(slist)):
                if self.proved(pkey, skey, k):
                    continue
                ckey, clist = self.child(plist, slist, k)
                if ckey != pkey and ckey in self.nodes:     # this part was refined further: go down
                    visit(ckey, clist, depth + 1)
                    continue
                rs = self.rows(pkey, skey, k)
                leaf = dict(case=self.case, parent=plist, split=slist, part=k, region=clist, depth=depth,
                            best=None, runtime=None, file=None)
                if rs:
                    with_bound = [r for r in rs if r.objbound is not None]
                    best = min(with_bound, key=lambda r: r.objbound) if with_bound else rs[0]
                    leaf.update(reason='UNRESOLVED', best=best.objbound, runtime=as_float(best.get('runtime')),
                                file=best.path, detail=f'{len(rs)} row(s), verdicts {sorted(Counter(str(r.verdict) for r in rs).items())}')
                else:
                    leaf.update(reason='MISSING', detail='part never run (or only rejected rows)')
                leaves.append(leaf)

        visit('[]', [], 0)
        return leaves

    def reachable(self):
        """Prefix keys reachable from the root through ANY split (used to find unattached rows)."""
        todo, seen = [('[]', [])], set()
        while todo:
            pkey, plist = todo.pop()
            if pkey in seen or pkey not in self.nodes:
                continue
            seen.add(pkey)
            for skey in self.nodes[pkey]:
                slist = self.split_of[skey]
                for k in range(2 ** len(slist)):
                    todo.append(self.child(plist, slist, k))
        return seen

    def max_depth(self, pkey='[]', plist=None, memo=None):
        """Number of split levels below this node that have rows (summarize.py gives up below 20)."""
        plist = [] if plist is None else plist
        memo = {} if memo is None else memo
        if pkey not in memo:
            best = 0
            for skey in self.nodes.get(pkey, {}):
                slist = self.split_of[skey]
                for k in range(2 ** len(slist)):
                    ckey, clist = self.child(plist, slist, k)
                    if ckey != pkey and ckey in self.nodes:
                        best = max(best, 1 + self.max_depth(ckey, clist, memo))
            memo[pkey] = best
        return memo[pkey]


# ----------------------------------------------------------------------------------------------- plan
def load_candidates(arg, n):
    if arg is None:
        cands = [t for t in DEFAULT_CANDIDATES if max(t) < n] + [list(t) for t in itertools.combinations(range(4, n), 3)]
    else:
        text = open(arg).read() if os.path.isfile(arg) else arg
        cands = json.loads(text)
        if not isinstance(cands, list):
            raise ValueError('--candidates must be a JSON list of [i,j,k] triangles')
    good, bad = [], []
    for t in cands:
        if isinstance(t, list) and len(t) == 3 and all(is_int(i) for i in t) and 0 <= t[0] < t[1] < t[2] < n:
            if t not in good:
                good.append(t)
        else:
            bad.append(t)
    return good, bad


def propose_split(case, n, plist, candidates, size):
    """First `size` candidates not fixed in the prefix and not forced (T+ / T-) in this case."""
    fixed = {tuple(t) for t, _ in plist}
    forced = forced_triangles(case, n)
    return [t for t in candidates if tuple(t) not in fixed and tuple(t) not in forced][:size]


def batch_problem(node, n):
    """Why the batch workflow would refuse this node (None if it accepts it)."""
    if node['case'] != 'boundary':
        return 'the batch workflow runs only the boundary case'
    forced = forced_triangles('boundary', n)
    tri_ok = lambda t: 0 <= t[0] < t[1] < t[2] < n and tuple(t) not in forced
    if not 1 <= len(node['split']) <= BATCH_MAX_SPLIT:
        return f'the batch workflow needs a split of 1 to {BATCH_MAX_SPLIT} triangles'
    if not all(tri_ok(t) for t in node['split']) or len({tuple(t) for t in node['split']}) != len(node['split']):
        return 'split has an unsorted, repeated, out-of-range or always-positive triangle'
    if not all(tri_ok(t) and s in (0, 1) for t, s in node['prefix']):
        return 'prefix has an unsorted, out-of-range or always-positive triangle, or a sign other than 0/1'
    fixed = [tuple(t) for t, _ in node['prefix']]
    if len(set(fixed)) != len(fixed) or set(fixed) & {tuple(t) for t in node['split']}:
        return 'prefix repeats a triangle or overlaps the split'
    return None


def make_plan(leaves, n, candidates, size):
    """One plan node per UNRESOLVED leaf (split it further) and one per (region, split) with MISSING parts
    (run those parts again with the original prefix and split)."""
    nodes, missing = [], {}
    for lf in leaves:
        if lf['reason'] == 'MISSING' and lf['split'] is None:          # a case never run at all
            if lf['case'] == 'vertices':
                split, note = [], 'corners case never run: run it unsplit (as the workflows do)'
            else:
                split = [[2, 3, k] for k in range(4, n)]
                note = 'boundary case never run: run the first-wave split of the README'
            nodes.append(dict(case=lf['case'], prefix=[], split=split, parts=list(range(2 ** len(split))),
                              reason='MISSING', best_bound=None, note=note))
        elif lf['reason'] == 'MISSING':
            key = (lf['case'], compact(lf['parent']), compact(lf['split']))
            if key not in missing:
                missing[key] = dict(case=lf['case'], prefix=lf['parent'], split=lf['split'], parts=[],
                                    reason='MISSING', best_bound=None,
                                    note='re-run these parts with their original prefix and split')
                nodes.append(missing[key])
            missing[key]['parts'].append(lf['part'])
        else:
            split = propose_split(lf['case'], n, lf['region'], candidates, size)
            note = f'refine part {lf["part"]} of split {compact(lf["split"])}'
            if len(split) < size:
                note += f'; only {len(split)} candidate triangle(s) left (give more with --candidates)'
            if not split:
                note += '; no candidate left, so this re-runs the region unsplit'
            nodes.append(dict(case=lf['case'], prefix=lf['region'], split=split, parts=list(range(2 ** len(split))),
                              reason='UNRESOLVED', best_bound=lf['best'], note=note))
    return nodes


# ----------------------------------------------------------------------------------------------- output
def sanitise(text, width=80):
    text = re.sub(r'[^A-Za-z0-9._-]+', '_', text).strip('_')
    return (text or 'root')[:width]


def write_copy(row, folder, name):
    """Write the exact bytes this tool analysed and check them back."""
    os.makedirs(folder, exist_ok=False)
    dest = os.path.join(folder, name)
    with open(dest, 'wb') as f:
        f.write(row.raw)
    with open(dest, 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == row.sha, f'copy of {row.path} differs'
    row.copied_to = dest
    return dest


def run_summarize(path, outdir):
    """Run summarize.py over OUTDIR and pick out its verdict lines."""
    res = dict(ran=False, verdict='not run', boundary=None, corners=None, same=None, lines=[], error='')
    if not path:
        res['error'] = 'skipped (--summarize "")'
        return res
    if not os.path.isfile(path):
        res['error'] = f'summarize.py not found at {path}'
        return res
    md = os.path.join(outdir, 'summary_summarize.md')
    try:
        p = subprocess.run([sys.executable, path, outdir, '--md', md], capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        res['error'] = 'summarize.py timed out after 900 s'
        return res
    res['ran'] = True
    out = p.stdout
    flag = lambda label: (m.group(1) == 'True') if (m := re.search(re.escape(label) + r': (True|False)', out)) else None
    res['boundary'] = flag('Boundary case fully covered by proved parts')
    res['corners'] = flag('Corners-occupied case proved')
    res['same'] = flag('All results use the same n and target')
    res['lines'] = [ln for ln in out.splitlines() if 'CERTIFIED' in ln or 'Not (yet)' in ln or 'no result files' in ln]
    if p.returncode != 0:
        res['verdict'] = f'ERROR (exit code {p.returncode})'
        res['error'] = p.stderr.strip()[-2000:]
    elif any(ln.startswith('**CERTIFIED') for ln in out.splitlines()):
        res['verdict'] = 'CERTIFIED'
    elif 'Not (yet) a complete certificate' in out:
        res['verdict'] = 'NOT CERTIFIED'
    elif 'no result files found' in out:
        res['verdict'] = 'NOT CERTIFIED (no result files)'
    else:
        res['verdict'] = 'UNKNOWN (output not recognised)'
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument('--n', type=int, required=True)
    ap.add_argument('--target', type=float, required=True)
    ap.add_argument('--roots', nargs='+', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--summarize', default='/home/user/heil/summarize.py')
    ap.add_argument('--candidates', default=None)
    ap.add_argument('--split-size', type=int, default=4)
    ap.add_argument('--hours', type=float, default=5.5)
    ap.add_argument('--label-prefix', default=None)
    a = ap.parse_args(argv)
    sys.setrecursionlimit(20000)
    now = datetime.datetime.now(datetime.timezone.utc)
    label_prefix = a.label_prefix if a.label_prefix is not None else now.strftime('r%m%d%H%M%S_')
    if not 1 <= a.split_size <= MAX_SPLIT:
        print(f'--split-size must be between 1 and {MAX_SPLIT}', file=sys.stderr)
        return 2
    if os.path.exists(a.out) and (not os.path.isdir(a.out) or os.listdir(a.out)):
        print(f'OUTDIR {a.out} exists and is not an empty folder; choose a new one (nothing was done).', file=sys.stderr)
        return 2
    try:
        candidates, bad_candidates = load_candidates(a.candidates, a.n)
    except (OSError, ValueError) as e:
        print(f'--candidates could not be read: {e}', file=sys.stderr)
        return 2
    os.makedirs(a.out, exist_ok=True)
    out_real = os.path.realpath(a.out)

    problems = []           # (path or '-', text): input problems -> exit code 2
    notes = []              # general notes for the report
    # 1. find and parse every result_*.json
    rows, parse_failures, seen_real, per_root = [], [], {}, Counter()
    for root in a.roots:
        if not os.path.isdir(root):
            problems.append((root, 'root folder not found'))
            continue
        if out_real == os.path.realpath(root) or out_real.startswith(os.path.realpath(root) + os.sep):
            notes.append(f'OUTDIR is inside root {root}: a later run over that root would read these copies again '
                         '(they would show up as byte-identical duplicates).')
        for path in sorted(glob.glob(os.path.join(glob.escape(root), '**', 'result_*.json'), recursive=True)):
            if not os.path.isfile(path) or os.path.realpath(path).startswith(out_real + os.sep):
                continue
            real = os.path.realpath(path)
            if real in seen_real:
                notes.append(f'{path} is the same file as {seen_real[real]} (reached from two roots); read once.')
                continue
            seen_real[real] = path
            per_root[root] += 1
            try:
                with open(path, 'rb') as f:
                    raw = f.read()
            except OSError as e:
                problems.append((path, f'cannot read: {e}'))
                continue
            try:
                data = json.loads(raw.decode('utf-8'))
                if not isinstance(data, dict):
                    raise ValueError('the file holds JSON but not an object')
            except (UnicodeDecodeError, ValueError, RecursionError) as e:
                problems.append((path, f'cannot parse: {type(e).__name__}: {e}'))
                parse_failures.append((root, path, raw))
                continue
            row = Row(root, path, raw, data)
            examine(row, a.n, a.target)
            for p in row.problems:
                problems.append((path, p))
            rows.append(row)

    kept = [r for r in rows if r.category == 'kept']
    ignored = Counter()
    for r in rows:
        if r.category == 'other_n':
            ignored[f"n = {r.get('n')} (not {a.n})"] += 1
        elif r.category == 'other_target':
            ignored[f"cutoff = {as_float(r.get('cutoff'))!r} (not {a.target!r})"] += 1
        elif r.category == 'broken':
            ignored['n or cutoff missing / not a number'] += 1

    # 4. BETTER rows (parsed ones, and unparseable files that contain the word)
    better = [r for r in rows if r.better_why]
    suspects = []           # unparseable files that mention BETTER: kept as Row objects with empty data
    for root, path, raw in parse_failures:
        if b'BETTER_CONFIGURATION_FOUND' in raw:
            m = re.search(rb'"n"\s*:\s*(\d+)', raw)
            s = Row(root, path, raw, {})
            s.n_guess = int(m.group(1)) if m else None
            suspects.append(s)
    better_same_n = [r for r in better if r.get('n') == a.n]
    suspect_same_n = [s for s in suspects if s.n_guess in (None, a.n)]

    # 5. duplicates and selection: one file per canonical key
    groups = {}
    for r in kept:
        if r.key is not None:
            groups.setdefault(r.key, []).append(r)
    chosen = []
    for key in sorted(groups, key=lambda k: (k[0], k[1], k[2], k[3])):
        valid = [r for r in groups[key] if r.valid]
        proved = [r for r in valid if r.verdict == 'PROVED']
        bound = lambda r, missing: (r.objbound if r.objbound is not None else missing, r.path)
        if proved:
            chosen.append(min(proved, key=lambda r: bound(r, -math.inf)))
        elif valid:
            chosen.append(min(valid, key=lambda r: bound(r, math.inf)))
    chosen_ids = {id(r) for r in chosen}
    counter = itertools.count(1)

    def origin(root, path):
        rel = os.path.relpath(os.path.dirname(path), root)
        base = os.path.basename(os.path.normpath(os.path.abspath(root)))
        return sanitise(base if rel == '.' else f'{base}_{rel}')

    for r in chosen:
        write_copy(r, os.path.join(a.out, f'{next(counter):04d}_{origin(r.root, r.path)}'), os.path.basename(r.path))
    side = os.path.join(a.out, 'better_other')
    for r in better:
        if id(r) in chosen_ids:
            continue
        summarize_safe = r.category == 'kept' and r.key is not None and not r.problems
        folder = f'{next(counter):04d}_{origin(r.root, r.path)}'
        if summarize_safe:
            write_copy(r, os.path.join(a.out, folder), os.path.basename(r.path))
        else:
            write_copy(r, os.path.join(side, folder), 'BETTER_' + os.path.basename(r.path))
    for s in suspects:
        write_copy(s, os.path.join(side, f'{next(counter):04d}_{origin(s.root, s.path)}'), 'UNPARSED_' + os.path.basename(s.path))

    # 6. text drift: same canonical split (or prefix) written differently
    split_texts, prefix_texts = {}, {}
    for r in kept:
        if r.key is not None:
            split_texts.setdefault(r.key[:3], set()).add(r.get('split'))
            prefix_texts.setdefault(r.key[:2], set()).add(r.get('prefix'))
    split_drift = {k: v for k, v in split_texts.items() if len(v) > 1}
    prefix_drift = {k: v for k, v in prefix_texts.items() if len(v) > 1}

    # 7. summarize.py over the copies
    summ = run_summarize(a.summarize, a.out)

    # 8. own coverage check
    valid_rows = [r for r in kept if r.valid]
    trees = {c: Tree(c, [r for r in valid_rows if r.key[0] == c]) for c in ('boundary', 'vertices')}
    cov = {c: trees[c].covered('[]', []) for c in trees}
    certified = cov['boundary'] and cov['vertices'] and not better_same_n and not suspect_same_n

    # 9. open leaves, unattached rows
    leaves = trees['boundary'].open_leaves() + trees['vertices'].open_leaves()
    unattached = {}
    for c, t in trees.items():
        reach = t.reachable()
        for pkey in t.nodes:
            if pkey not in reach:
                unattached[(c, pkey)] = sum(len(v) for s in t.nodes[pkey].values() for v in s.values())

    # 10. plan
    plan_nodes = make_plan(leaves, a.n, candidates, a.split_size)
    heil_dir = os.path.dirname(os.path.abspath(a.summarize)) if a.summarize else '/home/user/heil'
    hours_txt = repr(a.hours)
    for i, node in enumerate(plan_nodes, 1):
        node['label'] = f'{label_prefix}{i:02d}'
        node['batch_problem'] = batch_problem(node, a.n)
        if a.hours > 5.5 and node['batch_problem'] is None:
            node['batch_problem'] = 'hours > 5.5 (GitHub jobs stop at 6 h)'
    plan = dict(n=a.n, target=a.target, hours=a.hours,
                nodes=[dict(case=x['case'], prefix=x['prefix'], split=x['split'], parts=x['parts'],
                            reason=x['reason'], best_bound=x['best_bound'], note=x['note']) for x in plan_nodes])
    with open(os.path.join(a.out, 'plan.json'), 'w') as f:
        json.dump(plan, f, indent=1)
    with open(os.path.join(a.out, 'open_leaves.json'), 'w') as f:
        json.dump([dict(case=lf['case'], region=lf['region'], reason=lf['reason'], parent_prefix=lf['parent'],
                        split=lf['split'], part=lf['part'], best_bound=lf['best'], runtime=lf['runtime'], file=lf['file'])
                   for lf in leaves], f, indent=1)
    batch_nodes = [x for x in plan_nodes if x['batch_problem'] is None]
    batches, cur, cur_jobs = [], [], 0          # chunks of at most 256 jobs (one batch run each)
    for x in batch_nodes:
        if cur and cur_jobs + len(x['parts']) > BATCH_MAX_JOBS:
            batches.append(cur)
            cur, cur_jobs = [], 0
        entry = dict(prefix=x['prefix'], split=x['split'])
        if x['parts'] != list(range(2 ** len(x['split']))):
            entry['parts'] = x['parts']
        cur.append(entry)
        cur_jobs += len(x['parts'])
    if cur:
        batches.append(cur)

    # exit code
    if better_same_n or suspect_same_n:
        code = 3
    elif problems:
        code = 2
    else:
        code = 0 if certified else 1

    # ------------------------------------------------------------------ report
    L = []
    P = L.append
    yn = lambda b: 'yes' if b else 'no'
    tf = lambda b: '-' if b is None else ('True' if b else 'False')
    P(f'# Heilbronn n = {a.n}: combined results, independent coverage check and refinement plan')
    P('')
    P(f'Generated {now:%Y-%m-%d %H:%M} UTC by `{os.path.abspath(__file__)}`.')
    P(f'Target {a.target!r}. Roots: {", ".join(f"`{x}`" for x in a.roots)}. Output folder: `{os.path.abspath(a.out)}`.')
    P('')
    P('## Acronyms and terms')
    P('')
    P('| Term | Meaning |')
    P('|---|---|')
    P('| BETTER | Verdict BETTER_CONFIGURATION_FOUND: the solver\'s points, recomputed, have minimum area above the target |')
    P('| JSON | JavaScript Object Notation (format of the result files) |')
    P('| key | Canonical identity of a result: (case, sorted prefix, split in its order, part), texts without spaces |')
    P('| node / region | A set of configurations, given by its prefix (triangles with a fixed orientation) |')
    P('| prefix | Orientations already fixed: list of [[i,j,k], sign], sign 1 = positive, 0 = negative |')
    P('| split | Triangles whose orientation is split on; part p fixes split[i] to sign (p >> i) & 1 |')
    P('| T+ / T- | Triangles whose orientation heil_tri.py fixes itself (always positive / negative) |')
    P('| VM | Virtual Machine (the cloud session\'s 4-core computer) |')
    P('| zub | Upper bound on the minimum-area variable z in heil_tri.py; must be >= 0.5 for a valid proof |')
    P('')
    P('## 1. BETTER configurations (always listed first)')
    P('')
    if not better and not suspects:
        P('None.')
    for r in better:
        fails = []
        if r.category != 'kept':
            fails.append({'other_n': f"different n ({r.get('n')})", 'other_target': f"different target ({r.get('cutoff')!r})",
                          'broken': 'n or cutoff unreadable'}[r.category])
        fails += r.problems + r.rejects
        own_cut = as_float(r.get('cutoff'))
        above = lambda c: 'above' if r.recomputed is not None and c is not None and r.recomputed > c else 'not above'
        vs_target = (f', {above(a.target)} this run\'s target {a.target!r}' if r.get('n') == a.n and own_cut != a.target else '')
        P(f"- **{r.get('case')} part {r.get('part')}**, n = {r.get('n')}, cutoff {r.get('cutoff')!r}: "
          f"value (objval) {r.get('objval')!r}, recomputed min area (file) {r.get('recomputed_min_area')!r}, "
          f"recomputed here {r.recomputed!r} ({above(own_cut)} its cutoff{vs_target}).")
        P(f"  - why BETTER: {'; '.join(r.better_why)}")
        P(f"  - split `{r.get('split')}`, prefix `{short(r.get('prefix'), 200)}`")
        P(f"  - points: `{compact(r.get('points'))}`")
        P(f'  - file: `{r.path}`; copied to `{r.copied_to}`')
        P(f"  - {'fails other checks: ' + '; '.join(fails) if fails else 'passes all other checks'}"
          f"{'' if r.get('n') == a.n else ' (different n: does not affect this n)'}")
    for s in suspects:
        P(f'- **Unparseable file containing the text BETTER_CONFIGURATION_FOUND** (n looks like {s.n_guess}): `{s.path}`; '
          f'copied to `{s.copied_to}`. Inspect it by hand.')
    if better or suspects:
        P('')
        P('**Check every BETTER configuration exactly with verify_config.py before anything else.**')
    P('')
    P('## 2. Verdict')
    P('')
    P('| Check | This tool (independent) | summarize.py on OUTDIR |')
    P('|---|---|---|')
    P(f"| Boundary case covered | {yn(cov['boundary'])} | {tf(summ['boundary'])} |")
    P(f"| Corners (vertices) case covered | {yn(cov['vertices'])} | {tf(summ['corners'])} |")
    P(f"| Same n and target in the rows used | yes (only n = {a.n}, cutoff = {a.target!r}; zub >= {ZUB_MIN}) | {tf(summ['same'])} |")
    P(f"| No BETTER row for n = {a.n} | {yn(not better_same_n and not suspect_same_n)} | - |")
    P(f"| **Overall** | **{'CERTIFIED' if certified else 'NOT CERTIFIED'}** | **{summ['verdict']}** |")
    P('')
    if summ['error']:
        P(f"summarize.py: {summ['error']}")
        P('')
    for ln in summ['lines']:
        P(f'summarize.py said: {ln}')
    if summ['ran']:
        P('')
    disagree = summ['ran'] and ((summ['verdict'] == 'CERTIFIED') != certified or
                                (summ['boundary'] is not None and summ['boundary'] != cov['boundary']) or
                                (summ['corners'] is not None and summ['corners'] != cov['vertices']))
    if disagree:
        P('**WARNING: this tool and summarize.py disagree.** Likely causes found in the data:')
        causes = []
        if split_drift:
            causes.append('raw-split whitespace: the same split is written with different spacing (section 6), '
                          'and summarize.py compares split texts, so it does not combine those parts')
        hole = [r for r in valid_rows if r.key[0] == 'vertices' and r.verdict == 'PROVED' and r.get('prefix') == '[]'
                and r.split_list]
        if hole and not cov['vertices']:
            causes.append('summarize.py vertices hole (its line 71): it accepts any PROVED corners row with prefix "[]", '
                          f'even a single part of a split corners run ({len(hole)} such row(s) here)')
        if any(r.key[0] == 'vertices' and r.key[1] == '[]' and r.get('prefix') != '[]' for r in valid_rows):
            causes.append('a corners row with an empty prefix written other than exactly "[]" (summarize.py compares the text)')
        if any(r.category == 'kept' and r.get('n') == a.n for r in better) and not certified:
            causes.append('BETTER rows block this tool\'s certificate')
        if any(r.category != 'kept' and r.get('n') == a.n for r in better):
            causes.append('a BETTER row for another target was not given to summarize.py but blocks this tool')
        if cov['boundary'] and trees['boundary'].max_depth() > 20:
            causes.append('the proof tree is deeper than 20 levels, where summarize.py stops looking')
        dup_groups = [k for k, v in groups.items() if len(v) > 1]
        if dup_groups:
            causes.append(f'duplicate rows ({len(dup_groups)} keys, section 5): OUTDIR holds one file per key, so they do not '
                          'affect this summarize.py run, but they would shadow each other if summarize.py read the raw roots')
        if not causes:
            causes.append('no known cause found: compare section 8 with summary_summarize.md by hand')
        for c in causes:
            P(f'- {c}')
        P('')
    meaning = {3: 'a BETTER row for this n exists', 2: 'input problems (section 3)', 0: 'CERTIFIED', 1: 'not certified'}
    P(f'Exit code: **{code}** ({meaning[code]}).')
    if code == 2 and certified:
        P('The coverage check passes, but resolve the input problems before relying on it.')
    P('')
    P('## 3. Input problems')
    P('')
    if not problems:
        P('None.')
    for path, text in problems:
        P(f'- `{path}`: {text}')
    P('')
    P('## 4. Rows read')
    P('')
    for root in a.roots:
        P(f'- `{root}`: {per_root[root]} result file(s)')
    P(f'- parsed: {len(rows)}; kept (n = {a.n}, cutoff = {a.target!r}): {len(kept)}; valid for proof: {len(valid_rows)}; '
      f'copied into OUTDIR: {len(chosen)} (one per key) + BETTER copies')
    for reason, cnt in sorted(ignored.items()):
        P(f'- ignored, {reason}: {cnt}')
    P(f"- verdicts of kept rows: {dict(Counter(r.verdict for r in kept))}")
    for x in notes:
        P(f'- note: {x}')
    P('')
    P('## 5. Rejected rows, warnings and duplicates')
    P('')
    rej = [r for r in kept if r.rejects]
    P(f'Rejected for proof ({len(rej)}; reported but never counted as PROVED):')
    for r in rej:
        P(f"- `{r.path}` ({r.get('case')} part {r.get('part')}, verdict {r.verdict}): {'; '.join(r.rejects)}")
    warned = [r for r in kept if r.warnings]
    P('')
    P(f'Triangle warnings ({len(warned)} row(s); these rows still count, because heil_tri.py then solves a larger region):')
    for r in warned:
        P(f"- `{r.path}`: {'; '.join(r.warnings)}")
    if bad_candidates:
        P(f'- candidate triangles skipped (not sorted distinct triples in 0..{a.n - 1}): {bad_candidates}')
    dups = {k: v for k, v in groups.items() if len(v) > 1}
    identical = {k: v for k, v in dups.items() if len({r.sha for r in v}) == 1}
    differing = {k: v for k, v in dups.items() if k not in identical}
    P('')
    P(f'Duplicate keys: {len(dups)}. Of these, {len(identical)} have only byte-identical copies (the same result saved '
      f'in several places; harmless), {len(differing)} have different contents:')
    if identical:
        example = identical[sorted(identical)[0]]
        P(f"- example of byte-identical copies: {' = '.join(f'`{r.path}`' for r in example)}")
    for k, v in sorted(differing.items()):
        pick = next((r.path for r in v if id(r) in chosen_ids), 'none (no valid row)')
        P(f"- {k[0]} prefix `{short(k[1], 80)}` split `{k[2]}` part {k[3]}: "
          f"{', '.join(f'{r.verdict} (bound {r.objbound!r})' for r in v)}; copied: `{pick}`")
        for r in v:
            P(f"  - `{r.path}`: {r.verdict}, bound {r.objbound!r}, runtime {r.get('runtime')!r}"
              f"{'' if r.valid else ' (rejected: ' + '; '.join(r.rejects + r.problems) + ')'}")
    P('')
    P('## 6. Text drift (summarize.py compares split texts)')
    P('')
    if not split_drift and not prefix_drift:
        P('None.')
    for (c, pk, sk), texts in sorted(split_drift.items()):
        P(f"- **summarize.py will not combine these**: {c} prefix `{short(pk, 80)}`, split {sk} is written as "
          f"{', '.join(repr(t) for t in sorted(texts))}. This tool combines them. Use the compact form without spaces.")
    for (c, pk), texts in sorted(prefix_drift.items()):
        extra = (' summarize.py\'s corners check needs exactly "[]".' if c == 'vertices' and pk == '[]' else
                 ' Both tools sort prefixes, so this is harmless.')
        P(f"- {c} prefix `{short(pk, 80)}` is written in {len(texts)} different ways.{extra}")
    P('')
    P('## 7. Open regions (depth-first; at each region the split with most PROVED parts is followed)')
    P('')
    if not leaves:
        P('None: both trees are fully covered.')
    else:
        P(f"{sum(lf['reason'] == 'UNRESOLVED' for lf in leaves)} UNRESOLVED and {sum(lf['reason'] == 'MISSING' for lf in leaves)} "
          'MISSING leaves. MISSING parts of one split are grouped on one line; every leaf with its full region prefix '
          'is in `open_leaves.json`.')
        P('')
    shown = set()
    for lf in leaves:
        if lf['split'] is None:
            P(f"- {lf['case']} **MISSING**: the whole case ({lf['detail']})")
        elif lf['reason'] == 'MISSING':
            group = (lf['case'], compact(lf['parent']), compact(lf['split']))
            if group in shown:
                continue
            shown.add(group)
            parts = [x['part'] for x in leaves if x['reason'] == 'MISSING' and x['split'] is not None
                     and (x['case'], compact(x['parent']), compact(x['split'])) == group]
            P(f"- {lf['case']} **MISSING**: parts {ranges(parts)} of split `{group[2]}` at prefix `{short(group[1], 120)}` "
              '(never run, or only rejected rows)')
        else:
            rt = '' if lf['runtime'] is None else f", runtime {lf['runtime']:.0f} s"
            P(f"- {lf['case']} **UNRESOLVED**: part {lf['part']} of split `{compact(lf['split'])}` at prefix "
              f"`{short(compact(lf['parent']), 120)}`, best bound {lf['best']!r}{rt}; region to refine "
              f"`{short(compact(lf['region']), 200)}`")
    if unattached:
        P('')
        P('Rows at regions that cannot be reached from the root through any split (they do not count):')
        for (c, pk), cnt in sorted(unattached.items()):
            P(f'- {c} prefix `{short(pk, 120)}`: {cnt} row(s)')
    P('')
    P('## 8. Plan for the next runs')
    P('')
    if not plan_nodes:
        P('Nothing to run.')
    else:
        n_jobs = sum(len(x['parts']) for x in plan_nodes)
        P(f'{len(plan_nodes)} region(s), {n_jobs} job(s) in total, {hours_txt} h each. Written to `plan.json`.')
        if any(x['reason'] == 'MISSING' for x in plan_nodes):
            P('MISSING parts may simply still be running (for example in a GitHub run whose results have not landed '
              'yet): check that before starting them again.')
        P('')
        P('### (a) Batch workflow (heilbronn-batch): paste into the input "nodes"')
        P('')
        if batches:
            for i, b in enumerate(batches, 1):
                jobs = sum(len(e.get('parts', range(2 ** len(e['split'])))) for e in b)
                P(f'Batch run {i} of {len(batches)} ({jobs} jobs; also set n = {a.n}, target = {a.target!r}, hours = {hours_txt}):')
                P('')
                P('```')
                P(compact(b))
                P('```')
                P('')
        else:
            P('No region of this plan can go into the batch workflow (see below).')
            P('')
        excluded = [x for x in plan_nodes if x['batch_problem']]
        if excluded:
            P('Not in the batch value (use the classic workflow or the VM):')
            for x in excluded:
                P(f"- {x['label']}: {x['batch_problem']}")
            P('')
        P('### (b) Classic workflow (heilbronn-certify), one run per region')
        P('')
        for x in plan_nodes:
            bound_txt = '' if x['best_bound'] is None else f", best bound so far {x['best_bound']!r}"
            P(f"**{x['label']}** - {x['case']}, {x['reason']}{bound_txt}; {x['note']}; parts {ranges(x['parts'])}")
            P('')
            if x['case'] == 'boundary':
                P('```')
                P(f'n: {a.n}')
                P(f'target: {a.target!r}')
                P(f"split: {compact(x['split'])}")
                P(f"parts: {compact(x['parts'])}")
                P(f"prefix: {compact(x['prefix'])}")
                P('run_vertices: false')
                P(f'hours: {hours_txt}')
                P('```')
            elif not x['split'] and not x['prefix']:
                P('Classic workflow: run it with run_vertices = true (its corners job is unsplit).')
            else:
                P('Classic workflow: not possible (its corners job cannot take a split or prefix); use the VM command below.')
            P('')
        P('### (c) VM commands')
        P('')
        P('Run them in the folder that holds run_parts.sh. Each command starts a background job that runs its parts '
          'one after another on all cores, then writes results/cloud/<label>/DONE; start the next command only after '
          'that DONE file exists, so that jobs do not compete for the cores.')
        P('')
        P('```')
        P(f'cd {heil_dir}')
        secs = int(a.hours * 3600)
        for x in plan_nodes:
            lab = x['label']
            if x['case'] == 'boundary':
                P(f"bash run_parts.sh {lab} {a.n} {a.target!r} '{compact(x['split'])}' '{compact(x['prefix'])}' "
                  f"{hours_txt} {' '.join(map(str, x['parts']))}")
            elif not x['split'] and not x['prefix']:
                P(f"bash run_parts.sh {lab} {a.n} {a.target!r} '[]' '[]' {hours_txt} vertices")
            else:   # split corners case: run_parts.sh cannot do it, so call heil_tri.py directly
                P(f"mkdir -p results/cloud/{lab} && nohup bash -c 'for p in {' '.join(map(str, x['parts']))}; do "
                  f"python3 heil_tri.py --n {a.n} --case vertices --cutoff {a.target!r} --split \"{compact(x['split'])}\" "
                  f"--part $p --prefix \"{compact(x['prefix'])}\" --threads $(nproc) --timelimit {secs} "
                  f"--out results/cloud/{lab}/result_vertices_$p.json > results/cloud/{lab}/log_vertices_$p.txt 2>&1; done; "
                  f"echo ALL_DONE > results/cloud/{lab}/DONE' > /dev/null 2>&1 &")
        P('```')
        clash = [x['label'] for x in plan_nodes if os.path.exists(os.path.join(heil_dir, 'results', 'cloud', x['label']))]
        if clash:
            P('')
            P(f'**Warning: result folders already exist for labels {clash}; choose another --label-prefix.**')
    P('')
    P('## 9. All kept rows')
    P('')
    P('| case | prefix (sorted) | split | part | verdict | status | runtime (s) | bound | best found | used | file |')
    P('|---|---|---|---|---|---|---|---|---|---|---|')
    for r in sorted(kept, key=lambda r: (r.key or ('~',), r.path)):
        use = 'copied' if r.copied_to else ('rejected' if r.rejects or r.problems else 'duplicate')
        rt = as_float(r.get('runtime'))
        P(f"| {r.get('case')} | `{short(r.key[1] if r.key else r.get('prefix'), 50)}` | `{r.key[2] if r.key else r.get('split')}` | "
          f"{r.get('part')} | {r.verdict} | {r.get('status')} | {'-' if rt is None else f'{rt:.0f}'} | {r.get('objbound')} | "
          f"{r.get('objval')} | {use} | `{r.path}` |")
    report = '\n'.join(L) + '\n'
    with open(os.path.join(a.out, 'report.md'), 'w') as f:
        f.write(report)
    print(report)
    return code


if __name__ == '__main__':
    sys.exit(main())
