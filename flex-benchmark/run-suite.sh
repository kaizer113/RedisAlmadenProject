#!/bin/bash
set -euo pipefail
cd /home/ec2-user/flex-benchmark
.venv/bin/python validate.py --population 140000000
sleep 30
.venv/bin/python - <<'PY'
import json,platform,subprocess,time
from common import *
c=client()
save(ROOT/'results/environment.json',{'platform':platform.platform(),'python':platform.python_version(),'cpu':subprocess.check_output(['lscpu'],text=True),'server':c.info('server'),'before_benchmarks':snapshot(c),'codec':json.loads((ROOT/'codec-manifest.json').read_text()),'packages':subprocess.check_output([str(ROOT/'.venv/bin/pip'),'freeze'],text=True)})
PY
.venv/bin/python -u bench.py --duration 180 --warmup 30 --population 140000000
.venv/bin/python - <<'PY'
from common import *
c=client();snap=snapshot(c);assert snap['dbsize']==280000000
save(ROOT/'results/after-benchmarks.json',snap)
print('ALL BENCHMARKS COMPLETE')
PY
