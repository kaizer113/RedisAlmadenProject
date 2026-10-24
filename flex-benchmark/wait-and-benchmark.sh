#!/bin/bash
set -euo pipefail
cd /home/ec2-user/flex-benchmark
while ! test -f results/loaded.json; do
  if test -f STOP_LOAD; then echo 'Load stopped; benchmarks not started'; exit 1; fi
  sleep 10
done
bash run-suite.sh
