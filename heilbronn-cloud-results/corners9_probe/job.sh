for p in vertices; do
  if [ "$p" = vertices ]; then
    python3 heil_tri.py --n 9 --case vertices --cutoff 0.027426211734693878 --threads $(nproc) --timelimit 3600 --out results/cloud/corners9_probe/result_vertices_0.json > results/cloud/corners9_probe/log_vertices.txt 2>&1
  else
    python3 heil_tri.py --n 9 --case boundary --cutoff 0.027426211734693878 --split '[]' --part $p --prefix '[]' --threads $(nproc) --timelimit 3600 --out results/cloud/corners9_probe/result_boundary_$p.json > results/cloud/corners9_probe/log_$p.txt 2>&1
  fi
done
echo ALL_DONE > results/cloud/corners9_probe/DONE
