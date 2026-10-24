#!/bin/bash
set -euo pipefail
cd /home/ec2-user/flex-benchmark
while ! grep -q '"mode": "lz4", "batch_size": 1,' suite.log; do sleep 1; done
# Completed result was logged only after all raw timings were written and checks passed.
pkill -TERM -f '^.venv/bin/python -u bench.py --duration 180' || true
sleep 2
echo 'Continuing remaining tests with distinct per-batch-size random seeds.' >> suite.log
.venv/bin/python -u bench.py --duration 180 --warmup 30 --population 140000000 >> suite.log 2>&1
.venv/bin/python - <<'PY' >> suite.log
from common import *
c=client();snap=snapshot(c);assert snap['dbsize']==280000000
save(ROOT/'results/after-benchmarks.json',snap)
print('ALL BENCHMARKS COMPLETE')
PY
