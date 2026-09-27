for p in 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if [ "$p" = vertices ]; then
    python3 heil_tri.py --n 9 --case vertices --cutoff 0.027426211734693878 --threads $(nproc) --timelimit 60 --out results/cloud/split31_C/result_vertices_0.json > results/cloud/split31_C/log_vertices.txt 2>&1
  else
    python3 heil_tri.py --n 9 --case boundary --cutoff 0.027426211734693878 --split '[[0,2,4],[0,2,5],[1,3,7],[1,3,8]]' --part $p --prefix '[[[2,3,4],1],[[2,3,5],1],[[2,3,6],1],[[2,3,7],1],[[2,3,8],1]]' --threads $(nproc) --timelimit 60 --out results/cloud/split31_C/result_boundary_$p.json > results/cloud/split31_C/log_$p.txt 2>&1
  fi
done
echo ALL_DONE > results/cloud/split31_C/DONE
