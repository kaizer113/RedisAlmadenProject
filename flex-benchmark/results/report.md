# Redis Flex: private-VPC read benchmarks

VM: `i-0de54e8f19f72c179` (`c7i.4xlarge`, 16 vCPU), `10.0.1.160`, us-west-2a. Redis subscription `3460610`, database `14715459` (`redis-flex-1tb`), us-west-2. All Redis traffic used the private endpoint `even-biodegradable-big-13523.db.redis.io:17850` through VPC peering.

## Dataset and capacity

- Loaded **140,000,000 plain Strings and 140,000,000 LZ4 Strings**, 280,000,000 keys in total.
- Reported database `used_memory` after loading: **919.417 GB** (856.274 GiB). This endpoint metric is not a measurement of RAM alone on Flex.
- Provisioned size stayed at 1,000 GB, RAM percentage 20, 20 shards, replication disabled. No TTLs or indexes were added.
- Validation: 1,000 sampled plain documents and 1,000 sampled LZ4 documents matched the source data and UUIDs.
- Loading used short Lua batches of 256 same-slot keys, spread over 4,096 buckets (3,808 distinct slots). Sixteen VM processes loaded both formats together.

## Single-record GETs at 2,000 QPS

Latency below is client-observed GET response latency. Each test has a separate 30-second warm-up and 180-second measurement window.

| Format | Actual records/sec | p50 ms | p95 ms | p99 ms | Payload MB/s | Payload Mbit/s | Errors / misses |
|---|---:|---:|---:|---:|---:|---:|---:|
| plain | 2000.0 | 1.538 | 2.300 | 2.660 | 9.358 | 74.86 | 0 / 0 |
| lz4 | 2000.0 | 1.536 | 2.271 | 2.606 | 3.167 | 25.33 | 0 / 0 |

## Batch reads at 2,000 records/sec total

Batches are pipelines of independent GETs. Each latency is for the **entire batch** to finish. Rates are 200 batches/sec of 10, 20 batches/sec of 100, or 2 batches/sec of 1,000. Each format and size has 30 seconds of warm-up plus 180 measured seconds.

| Format | Records/batch | Batches/sec target | Actual records/sec | p50 ms | p95 ms | p99 ms | Payload MB/s | Errors / misses |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| plain | 10 | 200 | 2000.0 | 2.359 | 3.046 | 3.489 | 9.351 | 0 / 0 |
| lz4 | 10 | 200 | 2000.0 | 2.499 | 3.132 | 3.544 | 3.165 | 0 / 0 |
| plain | 100 | 20 | 2000.0 | 4.572 | 5.121 | 5.837 | 9.351 | 0 / 0 |
| lz4 | 100 | 20 | 2000.0 | 4.092 | 4.710 | 5.360 | 3.165 | 0 / 0 |
| plain | 1000 | 2 | 2000.0 | 20.490 | 23.919 | 25.954 | 9.352 | 0 / 0 |
| lz4 | 1000 | 2 | 2000.0 | 16.736 | 18.289 | 23.358 | 3.165 | 0 / 0 |

## LZ4 decode cost and scheduling

Read latency ends at response receipt. Application latency includes LZ4 decompression (no JSON parsing); scheduled-to-completion latency also includes any load-generator scheduling delay.

| Format | Batch | Read p99 ms | Application p50 ms | Application p95 ms | Application p99 ms | Scheduled-to-completion p99 ms | Scheduling lag p99 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| plain | 1 | 2.660 | 1.539 | 2.301 | 2.661 | 3.234 | 1.047 |
| lz4 | 1 | 2.606 | 1.540 | 2.274 | 2.609 | 3.185 | 1.044 |
| plain | 10 | 3.489 | 2.362 | 3.050 | 3.492 | 4.373 | 1.202 |
| lz4 | 10 | 3.544 | 2.529 | 3.162 | 3.575 | 4.423 | 1.230 |
| plain | 100 | 5.837 | 4.578 | 5.128 | 5.843 | 6.722 | 1.334 |
| lz4 | 100 | 5.360 | 4.247 | 4.867 | 5.513 | 6.450 | 1.348 |
| plain | 1000 | 25.954 | 20.536 | 23.964 | 26.000 | 31.786 | 10.224 |
| lz4 | 1000 | 23.358 | 18.343 | 19.709 | 24.989 | 28.642 | 6.515 |

## Network throughput

Payload rates above count returned value bytes. The table below includes calculated RESP framing and requests. These calculations exclude TCP/IP headers, retransmissions and link-layer overhead. VM NIC counters include background/SSH traffic; raw counter deltas are retained in each result. Decimal MB/s and Mbit/s are used.

| Format | Batch | RESP request MB/s | RESP response MB/s | RESP combined Mbit/s | Decoded data MB/s | VM NIC RX MB/s | VM NIC TX MB/s |
|---|---:|---:|---:|---:|---:|---:|---:|
| plain | 1 | 0.138 | 9.376 | 76.11 | 9.358 | 9.508 | 0.272 |
| lz4 | 1 | 0.134 | 3.185 | 26.55 | 9.358 | 3.317 | 0.267 |
| plain | 10 | 0.138 | 9.369 | 76.06 | 9.351 | 9.460 | 0.174 |
| lz4 | 10 | 0.134 | 3.183 | 26.54 | 9.351 | 3.228 | 0.164 |
| plain | 100 | 0.138 | 9.369 | 76.06 | 9.351 | 9.445 | 0.144 |
| lz4 | 100 | 0.134 | 3.183 | 26.54 | 9.351 | 3.212 | 0.139 |
| plain | 1000 | 0.138 | 9.370 | 76.06 | 9.352 | 9.445 | 0.144 |
| lz4 | 1000 | 0.134 | 3.183 | 26.54 | 9.352 | 3.210 | 0.138 |

## Reproducible key lookup

Index `i` ranges from zero through 139,999,999. Source pattern is `i % 10`; bucket is `i % 4096`. UUIDv8 is `b74613d0-2026-8abc-8def-` plus the index as 12 lowercase hex digits. Key is `plain:{BBBB}:UUID` or `lz4:{BBBB}:UUID`, with the bucket formatted as four lowercase hex digits. `common.py` implements this mapping. Both formats use identical index ranges and matching benchmark PRNG seeds within each batch size. Different batch sizes use different seeds to avoid reusing the same warmed key set.

## Interpretation and limits

- These are uniform random existing-key reads across each entire loaded population, with zero loader activity during measurement. They describe the observed mixed RAM/flash state after loading and warm-up; they do not isolate forced RAM hits or forced flash misses.
- Each single-record test has 360,000 scheduled GETs. Each 1,000-record batch test has only 360 measured batches, so its p99 is sensitive to a few observations. Raw latency arrays and per-second completions are included for further analysis.
- LZ4 values use standard independent-block frames with a literal UUID prefix block and a compressed JSON body block. They are individually decodable without shared dictionaries. This layout was chosen to enable fast Lua duplication and differs slightly from the earlier whole-document LZ4 test.
- The sample repeats ten source objects. Compression and cache behavior may differ with more varied real data. No claim of maximum sustainable throughput is made: these tests target 2,000 records/sec.
- VM is in us-west-2a in the consumer account. Redis reports us-west-2d in its own account; AZ letter names are account-specific, so physical same-AZ placement is not asserted.
- Benchmark connection retries are disabled. Errors and missing keys would fail the test; achieved throughput is required to be within 1% of the target. Rate matching is checked over the full window; per-second completion counts are provided.
- The VM and datasets remain available. AWS resources carry the requested owner and skip_deletion tags.

## Artifacts

- [Combined benchmark results](benchmark-summary.json)
- [Dataset validation](validation.json)
- [Loaded memory and key count](loaded.json)
- [Environment and package versions](environment.json)
- [VM, peering and route evidence](network-proof.json)
- [After-benchmark snapshot](after-benchmarks.json)
- [Final verification](verification.json)
- [Redis database configuration](redis-db-config.json)
- Per-test JSON and raw latency `.npz` files are alongside this report. Implementation and run instructions are in `../README.md`.
