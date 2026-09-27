for p in 0; do
  if [ "$p" = vertices ]; then
    python3 heil_tri.py --n 9 --case vertices --cutoff 0.027426211734693878 --threads $(nproc) --timelimit 600 --out results/cloud/s31A_c12/result_vertices_0.json > results/cloud/s31A_c12/log_vertices.txt 2>&1
  else
    python3 heil_tri.py --n 9 --case boundary --cutoff 0.027426211734693878 --split '[]' --part $p --prefix '[[[2,3,4],1],[[2,3,5],1],[[2,3,6],1],[[2,3,7],1],[[2,3,8],1],[[0,3,4],0],[[0,3,5],0],[[1,2,4],1],[[1,2,5],1]]' --threads $(nproc) --timelimit 600 --out results/cloud/s31A_c12/result_boundary_$p.json > results/cloud/s31A_c12/log_$p.txt 2>&1
  fi
done
echo ALL_DONE > results/cloud/s31A_c12/DONE
