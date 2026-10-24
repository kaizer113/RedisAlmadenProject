# Redis Flex load and private-VPC read benchmark

Target: subscription 3460610, database 14715459 (`redis-flex-1tb`), us-west-2, 1,000 GB, 20% RAM, 20 shards, no replication. Capacity stays unchanged. The final load contains exactly 140 million records per format (280 million keys). It fit without a resize or count reduction, reporting approximately 919.4 decimal GB used after loading.

## VM and network

- EC2: `i-0de54e8f19f72c179`, `c7i.4xlarge`, 16 vCPU, Amazon Linux 2023.
- VPC: `vpc-0bdba995c15e5371d`; subnet `subnet-0a5769ac32b192dad`.
- Private IP: `10.0.1.160`.
- Redis endpoint: `even-biodegradable-big-13523.db.redis.io:17850`.
- Redis network: `192.168.1.0/24`, peering `pcx-0d5e9a0c537f693f8`.
- The client asserts the endpoint resolves within the private Redis CIDR before connecting.
- SSH is restricted to the owner's laptop IP. All supported VM, disk, interface, key-pair, security-group and rule resources carry `owner=lionel_giavelli` and `skip_deletion=yes`.
- The benchmark VM and database were destroyed after the experiment. These IDs describe the historical run. Credentials and SSH keys remain excluded from Git.

## Dataset and reproducible keys

Each format repeats the same ten source objects, adding a unique identifier inside the document. Index `i`, starting at zero, identifies the source row as `i % 10` and the bucket as `i % 4096`.

UUIDv8: `b74613d0-2026-8abc-8def-` followed by the index as 12 lowercase hexadecimal digits.

Key: `plain:{BBBB}:UUID` or `lz4:{BBBB}:UUID`, where BBBB is the bucket as four lowercase hexadecimal digits. For example, index zero is `plain:{0000}:b74613d0-2026-8abc-8def-000000000000`.

This is an explicit reproducible identifier scheme, not a UUID collision probability assumption. It supports direct random access without storing hundreds of millions of key names. Final population sizes and successful load counts are in the results manifest. The two formats have separate namespaces and identical index ranges.

## Lua loading and compression

Sixteen loader processes send batches of 256 declared keys sharing one hash tag. The 4,096 buckets spread load across the shard space. Each short Lua call writes one batch, and checkpoints allow idempotent restart. Both formats advance together, preserving equal completed counts. No TTLs or indexes are created. Evictions or worker errors stop loading.

Plain values are compact JSON text with the UUID first. LZ4 values are standard independent-block frames: one literal UUID-prefix block plus one compressed JSON-body block. Every value is self-contained and decoded by the standard LZ4 library without an external dictionary. This lets Lua duplicate the compressed template without recompressing or uploading each full document. It differs slightly in frame overhead and compression layout from the earlier whole-document LZ4 test; do not assume those memory figures are identical.

Format reference: https://github.com/lz4/lz4/blob/dev/doc/lz4_Frame_format.md

## Read methodology

For each format separately:

- Single-record GET: 2,000 requests/sec, 30-second warm-up, at least 180 measured seconds.
- Batch 10: 200 batches/sec = 2,000 records/sec.
- Batch 100: 20 batches/sec = 2,000 records/sec.
- Batch 1,000: 2 batches/sec = 2,000 records/sec.
- Each batch is a pipeline of independent GET commands through the database endpoint. It is not an atomic multi-key operation.
- Batch latency measures completion of the entire batch, not a per-record latency estimate.
- Uniform random indices over the complete loaded population, with matching seeds across formats for each batch size, and different seeds between batch sizes to avoid reusing the same warmed key set.
- No public Redis endpoint, load overlap, or key misses are permitted in the measured runs.
- Open-loop pacing tracks scheduling delay and scheduled-to-completion latency to expose client backlog. Achieved rates must be within 1% of 2,000 records/sec.
- Read latency ends when the response arrives. LZ4 application latency additionally includes decompression; both are reported. JSON parsing is excluded for both formats.
- Raw timings are saved as compressed NumPy arrays alongside p50, p95, p99, p99.9, mean and max.
- Per-second completion counts and errors/misses are saved. No retries are hidden in benchmark code; connection failures fail the run.

Flex results represent the mixed RAM/flash state after loading and warm-up. The workload is uniformly random over a large dataset, not a deliberately warmed small working set. These tests do not separately characterize forced RAM hits and flash misses.

## Network measurements

Results include returned value bytes/sec and Mbit/sec; calculated RESP request/response traffic; decoded bytes/sec; VM interface RX/TX deltas; and Redis endpoint network counters. RESP estimates exclude TCP/IP headers, retransmits and link-layer overhead. VM interface counters include background VM/SSH traffic and are not claimed to isolate Redis packets perfectly. Decimal MB and Mbit are used.

## Execution on the VM

This repository preserves the experiment, not a live deployment. Before a new run, provision a new database and VM, update the database-ID and private-CIDR guards in `common.py`, and review the historical AWS IDs in `provision.py`. Copy `redis.json.example` to the ignored `redis.json` and set the new connection details locally.

Install dependencies and generate the Lua loaders from your private ten-object sample:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python prepare.py /path/to/sample.txt
```

Generated Lua files embed source documents and are intentionally excluded from Git, along with the original sample. The generator preserves the exact loader algorithm. Keep `benchmark/run.py` alongside this directory because it supplies the sample parser. For a fresh database, start with a fresh `results/` working directory; archived worker checkpoints must not be reused.

The committed `results/` files preserve measured results and raw timing arrays. The CSV is ready for Google Sheets. Private input documents and credentials are not required to inspect the results.

```sh
cd /home/ec2-user/flex-benchmark
.venv/bin/python load.py --pilot --pilot-sweeps 10
.venv/bin/python load.py
.venv/bin/python bench.py --duration 180 --warmup 30 --population FINAL_COUNT
```

Do not rerun the initial pilot after increasing the dataset: its exact key-count assertion expects the pilot population. Load checkpoints are idempotent and are retained. To stop loading gracefully, create `STOP_LOAD`; remove it only after understanding the reason for stopping. Credentials are in `redis.json` (mode 600).

Fetch a known record on the VM (same index identifies the same document in both formats):

```sh
.venv/bin/python lookup.py plain 42
.venv/bin/python lookup.py lz4 42
```

The keys are directly reconstructible; no key scan is needed. The final confirmed range is `0..139999999` for both namespaces.
