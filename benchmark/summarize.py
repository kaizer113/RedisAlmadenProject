import json, statistics
from pathlib import Path
root = Path(__file__).resolve().parent / 'results'
r = json.loads((root / 'report.json').read_text())
a = r['runs']['string']['after']['memory']['used_memory']
b = r['runs']['json']['after']['memory']['used_memory']
lines = ['# Redis String vs JSON: 1.6 million entries', '',
'Completed October 23, 2026. Subscription `3460170`, database `14714560`, AWS us-west-2. Redis 8.6.2; ReJSON module version 80606. Configured capacity: 25 GB; replication disabled.', '',
'## Measured database memory', '',
'| Measurement | Redis String | Redis JSON |','|---|---:|---:|']
for title, func in [
 ('Entries',lambda x:f"{x['after']['dbsize']:,}"),
 ('Used memory, exact bytes',lambda x:f"{x['after']['memory']['used_memory']:,}"),
 ('Used memory, decimal GB',lambda x:f"{x['after']['memory']['used_memory']/1e9:.3f}"),
 ('Used memory, binary GiB',lambda x:f"{x['after']['memory']['used_memory']/2**30:.3f}"),
 ('Empty baseline, bytes',lambda x:f"{x['before']['memory']['used_memory']:,}"),
 ('Increase over empty baseline, bytes',lambda x:f"{x['after']['memory']['used_memory']-x['before']['memory']['used_memory']:,}"),
 ('New evictions',lambda x:str(x['after']['stats']['evicted_keys']-x['before']['stats']['evicted_keys'])),
 ('Load duration, seconds (not a performance benchmark)',lambda x:f"{x['load_seconds']:.1f}")]:
 lines.append('| '+title+' | '+' | '.join(func(r['runs'][m]) for m in ['string','json'])+' |')
lines += ['',f'JSON used approximately **{(b/a-1)*100:.1f}% more database memory** ({b/a:.3f}×), a difference of {(b-a)/1e9:.3f} GB. These are measured INFO memory readings, not projected totals. GB = 1,000,000,000 bytes; GiB = 1,073,741,824 bytes.', '',
'## Method', '',
'The input contains 10 consecutive JSON objects. Each was copied 160,000 times. A deterministic UUIDv5 was added to each document as `uuid` and used in its `story:<uuid>` key. Both runs used identical keys and source-record distributions. The total compact serialized value payload, including UUID fields, was 7,484,000,000 bytes in each mode (JSON storage parses that payload into its native representation).', '',
'Ten generated Lua scripts (one per source record) duplicate the source content server-side. Each invocation writes one explicit key, using SET or JSON.SET, and the laptop pipelines 2,000 invocations per batch. This distributes keys normally across shards and avoids one long blocking Lua operation. The source JSON is joined as text with the UUID field, preserving arrays, nulls and numeric values.', '',
'The sequence was: verify empty → load Strings → settle and measure → clear with FLUSHDB ASYNC → verify zero keys and lazy-free completion → load JSON → settle and measure. All ten document patterns were checked for semantic equality in both passes. DBSIZE was verified every 100,000 writes. The JSON dataset remains in the database.', '',
'## Sampled per-key memory', '',
'MEMORY USAGE SAMPLES 0 was captured for 1,000 keys, evenly divided across the 10 source records. The following values are mean bytes per sampled key. They are diagnostic estimates; do not sum the JSON figures to derive actual database memory.', '',
'| Source record | String bytes/key | JSON bytes/key |', '|---|---:|---:|']
samples = {m:json.loads((root/f'{m}_key_samples.json').read_text()) for m in ['string','json']}
for i in range(1,11):
 lines.append(f'| {i} | '+ ' | '.join(f"{statistics.mean(x['memory_usage_bytes'] for x in samples[m] if x['record']==i):,.0f}" for m in ['string','json'])+' |')
lines += ['', '## Interpretation and limits', '',
'- This duplicates only ten source records. JSON can reuse repeated strings on a node, so these results should not be treated as sizing for 1.6 million independently varied records. Redis documents that JSON.DEBUG MEMORY counts repeated strings independently despite underlying reuse: https://redis.io/docs/latest/develop/data-types/json/ram/',
'- Database usage here is Redis Cloud endpoint INFO memory `used_memory`. It is not a screenshot or measurement from the Cloud console. The endpoint returned limited INFO fields; MEMORY STATS was forbidden and CONFIG GET maxmemory returned no value. Therefore no unsupported dataset-only or capacity-percent figures are claimed.',
'- Both passes had no TTLs, no replication, no persistence and no search indexes. UUID and key overhead are included. The capacity was not changed.',
'- Load durations include laptop/network/pipelining effects and are not a controlled throughput comparison.',
'- Public access remains enabled as requested, restricted to the laptop public IP and existing VPC CIDR. VPC peering tests were not performed by this benchmark.', '',
'## Artifacts', '',
'- [Raw combined report](report.json)',
'- [String full memory snapshot](string_full.json)',
'- [JSON full memory snapshot](json_full.json)',
'- [String per-key sample](string_key_samples.json)',
'- [JSON per-key sample](json_key_samples.json)',
'- Generated Lua scripts: `load_record_1.lua` through `load_record_10.lua`.',
'- Runner: `../run.py`; repeat runs require an empty database. Results and source data are excluded from Git.', '']
(root/'comparison.md').write_text('\n'.join(lines))
