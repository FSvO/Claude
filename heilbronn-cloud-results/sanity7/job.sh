for p in 0 1 2 3 4 5 6 7 vertices; do
  if [ "$p" = vertices ]; then
    python3 heil_tri.py --n 7 --case vertices --cutoff 0.04861597222222222 --threads $(nproc) --timelimit 360 --out results/cloud/sanity7/result_vertices_0.json > results/cloud/sanity7/log_vertices.txt 2>&1
  else
    python3 heil_tri.py --n 7 --case boundary --cutoff 0.04861597222222222 --split '[[2,3,4],[2,3,5],[2,3,6]]' --part $p --prefix '[]' --threads $(nproc) --timelimit 360 --out results/cloud/sanity7/result_boundary_$p.json > results/cloud/sanity7/log_$p.txt 2>&1
  fi
done
echo ALL_DONE > results/cloud/sanity7/DONE
