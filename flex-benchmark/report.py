import json,pathlib
ROOT=pathlib.Path(__file__).resolve().parent
R=ROOT/'results'
summary=json.loads((R/'benchmark-summary.json').read_text())
validation=json.loads((R/'validation.json').read_text())
loaded=json.loads((R/'loaded.json').read_text())
lines=['# Redis Flex: private-VPC read benchmarks','',
'VM: `i-0de54e8f19f72c179` (`c7i.4xlarge`, 16 vCPU), `10.0.1.160`, us-west-2a. Redis subscription `3460610`, database `14715459` (`redis-flex-1tb`), us-west-2. All Redis traffic used the private endpoint `even-biodegradable-big-13523.db.redis.io:17850` through VPC peering.','',
'## Dataset and capacity','',
f"- Loaded **{validation['population_per_format']:,} plain Strings and {validation['population_per_format']:,} LZ4 Strings**, {loaded['dbsize']:,} keys in total.",
f"- Reported database `used_memory` after loading: **{loaded['memory']['used_memory']/1e9:,.3f} GB** ({loaded['memory']['used_memory']/2**30:,.3f} GiB). This endpoint metric is not a measurement of RAM alone on Flex.",
'- Provisioned size stayed at 1,000 GB, RAM percentage 20, 20 shards, replication disabled. No TTLs or indexes were added.',
f"- Validation: {validation['sample_checks_per_format']['plain']:,} sampled plain documents and {validation['sample_checks_per_format']['lz4']:,} sampled LZ4 documents matched the source data and UUIDs.",
'- Loading used short Lua batches of 256 same-slot keys, spread over 4,096 buckets (3,808 distinct slots). Sixteen VM processes loaded both formats together.','',
'## Single-record GETs at 2,000 QPS','',
'Latency below is client-observed GET response latency. Each test has a separate 30-second warm-up and 180-second measurement window.','',
'| Format | Actual records/sec | p50 ms | p95 ms | p99 ms | Payload MB/s | Payload Mbit/s | Errors / misses |',
'|---|---:|---:|---:|---:|---:|---:|---:|']
for r in summary:
 if r['batch_size']==1:
  l=r['read_latency'];t=r['throughput']
  lines.append(f"| {r['mode']} | {r['achieved_records_per_second']:.1f} | {l['p50_ms']:.3f} | {l['p95_ms']:.3f} | {l['p99_ms']:.3f} | {t['value_payload_MB_per_second']:.3f} | {t['value_payload_Mbit_per_second']:.2f} | {r['errors']} / {r['misses']} |")
lines+=['','## Batch reads at 2,000 records/sec total','',
'Batches are pipelines of independent GETs. Each latency is for the **entire batch** to finish. Rates are 200 batches/sec of 10, 20 batches/sec of 100, or 2 batches/sec of 1,000. Each format and size has 30 seconds of warm-up plus 180 measured seconds.','',
'| Format | Records/batch | Batches/sec target | Actual records/sec | p50 ms | p95 ms | p99 ms | Payload MB/s | Errors / misses |',
'|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for r in summary:
 if r['batch_size']>1:
  l=r['read_latency'];t=r['throughput']
  lines.append(f"| {r['mode']} | {r['batch_size']} | {r['target_batches_per_second']:g} | {r['achieved_records_per_second']:.1f} | {l['p50_ms']:.3f} | {l['p95_ms']:.3f} | {l['p99_ms']:.3f} | {t['value_payload_MB_per_second']:.3f} | {r['errors']} / {r['misses']} |")
lines+=['','## LZ4 decode cost and scheduling','',
'Read latency ends at response receipt. Application latency includes LZ4 decompression (no JSON parsing); scheduled-to-completion latency also includes any load-generator scheduling delay.','',
'| Format | Batch | Read p99 ms | Application p50 ms | Application p95 ms | Application p99 ms | Scheduled-to-completion p99 ms | Scheduling lag p99 ms |',
'|---|---:|---:|---:|---:|---:|---:|---:|']
for r in summary:
 a=r['application_latency_including_lz4_decode']
 lines.append(f"| {r['mode']} | {r['batch_size']} | {r['read_latency']['p99_ms']:.3f} | {a['p50_ms']:.3f} | {a['p95_ms']:.3f} | {a['p99_ms']:.3f} | {r['scheduled_to_completion_latency']['p99_ms']:.3f} | {r['scheduling_lag']['p99_ms']:.3f} |")
lines+=['','## Network throughput','',
'Payload rates above count returned value bytes. The table below includes calculated RESP framing and requests. These calculations exclude TCP/IP headers, retransmissions and link-layer overhead. VM NIC counters include background/SSH traffic; raw counter deltas are retained in each result. Decimal MB/s and Mbit/s are used.','',
'| Format | Batch | RESP request MB/s | RESP response MB/s | RESP combined Mbit/s | Decoded data MB/s | VM NIC RX MB/s | VM NIC TX MB/s |',
'|---|---:|---:|---:|---:|---:|---:|---:|']
for r in summary:
 t=r['throughput'];rx=sum(x['rx_bytes'] for x in r['nic_byte_deltas'].values())/r['elapsed_seconds']/1e6;tx=sum(x['tx_bytes'] for x in r['nic_byte_deltas'].values())/r['elapsed_seconds']/1e6
 lines.append(f"| {r['mode']} | {r['batch_size']} | {t['resp_request_MB_per_second']:.3f} | {t['resp_response_MB_per_second']:.3f} | {t['resp_combined_Mbit_per_second']:.2f} | {t['decoded_MB_per_second']:.3f} | {rx:.3f} | {tx:.3f} |")
lines+=['','## Reproducible key lookup','',
'Index `i` ranges from zero through 139,999,999. Source pattern is `i % 10`; bucket is `i % 4096`. UUIDv8 is `b74613d0-2026-8abc-8def-` plus the index as 12 lowercase hex digits. Key is `plain:{BBBB}:UUID` or `lz4:{BBBB}:UUID`, with the bucket formatted as four lowercase hex digits. `common.py` implements this mapping. Both formats use identical index ranges and matching benchmark PRNG seeds within each batch size. Different batch sizes use different seeds to avoid reusing the same warmed key set.','',
'## Interpretation and limits','',
'- These are uniform random existing-key reads across each entire loaded population, with zero loader activity during measurement. They describe the observed mixed RAM/flash state after loading and warm-up; they do not isolate forced RAM hits or forced flash misses.',
'- Each single-record test has 360,000 scheduled GETs. Each 1,000-record batch test has only 360 measured batches, so its p99 is sensitive to a few observations. Raw latency arrays and per-second completions are included for further analysis.',
'- LZ4 values use standard independent-block frames with a literal UUID prefix block and a compressed JSON body block. They are individually decodable without shared dictionaries. This layout was chosen to enable fast Lua duplication and differs slightly from the earlier whole-document LZ4 test.',
'- The sample repeats ten source objects. Compression and cache behavior may differ with more varied real data. No claim of maximum sustainable throughput is made: these tests target 2,000 records/sec.',
'- VM is in us-west-2a in the consumer account. Redis reports us-west-2d in its own account; AZ letter names are account-specific, so physical same-AZ placement is not asserted.',
'- Benchmark connection retries are disabled. Errors and missing keys would fail the test; achieved throughput is required to be within 1% of the target. Rate matching is checked over the full window; per-second completion counts are provided.',
'- The VM and datasets remain available. AWS resources carry the requested owner and skip_deletion tags.','',
'## Artifacts','',
'- [Combined benchmark results](benchmark-summary.json)',
'- [Dataset validation](validation.json)',
'- [Loaded memory and key count](loaded.json)',
'- [Environment and package versions](environment.json)',
'- [VM, peering and route evidence](network-proof.json)',
'- [After-benchmark snapshot](after-benchmarks.json)',
'- [Final verification](verification.json)',
'- [Redis database configuration](redis-db-config.json)',
'- Per-test JSON and raw latency `.npz` files are alongside this report. Implementation and run instructions are in `../README.md`.','']
(R/'report.md').write_text('\n'.join(lines))
print('\n'.join(lines[:30]))
