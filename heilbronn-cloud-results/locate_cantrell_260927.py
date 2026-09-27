# Which n=9 parts (split on (2,3,k), k=4..8) contain Cantrell's configuration, under every affine symmetry of T
# and every admissible choice of p0,p1 (bottom edge), p2 (hypotenuse), p3 (left edge)?  Exact rational arithmetic.
import itertools
from fractions import Fraction as F
pts = [tuple(F(a, 56) for a in p) for p in [(49,7),(0,49),(7,0),(0,6),(50,0),(6,50),(10,22),(24,10),(22,24)]]
def area2(p, q, r):  # twice the signed area
    return (q[0]-p[0])*(r[1]-p[1]) - (r[0]-p[0])*(q[1]-p[1])
# the 6 affine maps of T permuting its corners, via barycentric coordinates (u,v,w) = (1-x-y, x, y) for corners (0,0),(1,0),(0,1)
def maps():
    for perm in itertools.permutations(range(3)):
        def f(p, perm=perm):
            b = (1 - p[0] - p[1], p[0], p[1]); nb = [None]*3
            for i in range(3): nb[perm[i]] = b[i]
            return (nb[1], nb[2])
        yield perm, f
split = [(2,3,4),(2,3,5),(2,3,6),(2,3,7),(2,3,8)]
minA = min(abs(area2(*t)) for t in itertools.combinations(pts, 3)) / 2
print('Cantrell min area =', minA, '=', float(minA))
found = {}
for perm, f in maps():
    Q = [f(p) for p in pts]
    bottom = [q for q in Q if q[1] == 0]; hyp = [q for q in Q if q[0] + q[1] == 1]; left = [q for q in Q if q[0] == 0]
    for p0, p1 in itertools.permutations(bottom, 2):
        if not (p0[0] <= p1[0] and p0[0] + p1[0] <= 1): continue
        for p2 in hyp:
            for p3 in left:
                if len({p0, p1, p2, p3}) < 4: continue
                rest = sorted([q for q in Q if q not in (p0, p1, p2, p3)], key=lambda q: q[0])
                xs = [q[0] for q in rest]
                ties = len(set(xs)) < len(xs)
                P = [p0, p1, p2, p3] + rest
                signs = [1 if area2(P[i], P[j], P[k]) > 0 else 0 for (i, j, k) in split]
                part = sum(s << i for i, s in enumerate(signs))
                # check the fixed T+ orientations hold
                tplus = [t for t in itertools.combinations(range(9), 3) if max(t) <= 3] + [(0, 1, k) for k in range(4, 9)]
                ok = all(area2(P[i], P[j], P[k]) >= 0 for (i, j, k) in tplus)
                found.setdefault(part, []).append((perm, ok, ties))
for part in sorted(found):
    print('part', part, 'embeddings:', len(found[part]), 'T+ ok:', all(o for _, o, _ in found[part]), 'x-ties among free points:', any(t for *_, t in found[part]))
