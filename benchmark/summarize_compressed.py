"""Generate a measured comparison and explicitly labeled linear projections."""
import json, statistics
from pathlib import Path
root=Path(__file__).resolve().parent/'results'
original=json.loads((root/'report.json').read_text())
compressed=json.loads((root/'lz4_report.json').read_text())
runs={m:original['runs'][m] for m in ['string','json']};runs['lz4']=compressed
names={'string':'String','json':'Redis JSON','lz4':'LZ4 String'}
used={m:r['after']['memory']['used_memory'] for m,r in runs.items()}
net={m:r['after']['memory']['used_memory']-r['before']['memory']['used_memory'] for m,r in runs.items()}
lines=['# LZ4 compressed Redis Strings: measured memory and projections','',
'Completed October 23, 2026, from the laptop against database `14714560` in us-west-2. Configured capacity: 25 GB, replication disabled. Original String and JSON measurements are preserved.','',
'## Measured at 1,600,000 entries','',
'| Measurement | String | Redis JSON | LZ4 String |','|---|---:|---:|---:|']
for title,fn in [
 ('Entries',lambda r:f"{r['after']['dbsize']:,}"),
 ('Database used_memory, bytes',lambda r:f"{r['after']['memory']['used_memory']:,}"),
 ('Database used_memory, GB',lambda r:f"{r['after']['memory']['used_memory']/1e9:.3f}"),
 ('Database used_memory, GiB',lambda r:f"{r['after']['memory']['used_memory']/2**30:.3f}"),
 ('Empty baseline, bytes',lambda r:'Unsettled; excluded' if r is compressed else f"{r['before']['memory']['used_memory']:,}"),
 ('Increase over baseline, bytes',lambda r:'Not reported' if r is compressed else f"{r['after']['memory']['used_memory']-r['before']['memory']['used_memory']:,}"),
 ('New evictions',lambda r:str(r['after']['stats']['evicted_keys']-r['before']['stats']['evicted_keys']))]:
 lines.append('| '+title+' | '+' | '.join(fn(runs[m]) for m in runs)+' |')
lines+=['',f"LZ4 reduced measured database memory by approximately **{(1-used['lz4']/used['string'])*100:.1f}% versus uncompressed Strings** and **{(1-used['lz4']/used['json'])*100:.1f}% versus Redis JSON**.",'',
'## Linear projections','',
'These are rough extrapolations, not measured deployments or capacity commitments. For consistency with the preceding estimates, multiply the full measured database memory at 1.6 million entries by 100, 250 or 1,000. This scales total observed memory, including overhead; at large scale, actual shard topology and overhead will differ.','',
'| Entries | String, GB | Redis JSON, GB | LZ4 String, GB |','|---|---:|---:|---:|']
projections=[]
for count in [160_000_000,400_000_000,1_600_000_000]:
 projected={m:used[m]*count/1_600_000 for m in runs}
 projections.append({'entries':count,'projected_bytes':projected})
 lines.append(f'| {count:,} | '+' | '.join(f'{projected[m]/1e9:,.1f}' for m in runs)+' |')
lines+=['','Units: decimal GB = 10^9 bytes; TB = 10^12 bytes; GiB = 2^30 bytes. Projections exclude replication, indexes and operational headroom.','',
'## Compression method','',
f"Used **LZ4 frame, compression level 0**, with python-lz4 {compressed['python_lz4_version']}. LZ4 is designed for fast lossless compression; this experiment does not benchmark codec performance against other algorithms. References: https://lz4.org/ and https://python-lz4.readthedocs.io/en/stable/lz4.frame.html",'',
'Every complete compact JSON document, including its unique UUID, was independently compressed on the laptop. The UUIDs, keys and 160,000-copies-per-record distribution match the earlier passes. Stored values are standard LZ4 frame bytes: no Base64, no external dictionary, no cross-record compression. Lua stores each binary value in a Redis String. Applications must decompress it to access document fields.','',
f"- Uncompressed value payload: {compressed['uncompressed_value_bytes']:,} bytes.",
f"- Compressed value payload, including frame overhead: {compressed['compressed_value_bytes']:,} bytes.",
f"- Payload compression ratio: {compressed['uncompressed_value_bytes']/compressed['compressed_value_bytes']:.3f}:1.",
f"- Mean compressed payload: {compressed['compressed_value_bytes']/compressed['total_entries']:,.1f} bytes/entry.",
f"- Mean measured database memory: {used['lz4']/compressed['total_entries']:,.1f} bytes/entry.",
f"- Sample mean MEMORY USAGE: {statistics.mean(x['memory_usage_bytes'] for x in compressed['samples']):,.1f} bytes/key.",
f"- Verified {compressed['verified_roundtrips']:,} sampled byte-for-byte decompression round trips, semantic JSON equality, and Redis String types.",
f"- Load duration: {compressed['load_seconds']:.1f} seconds. This includes laptop upload and is not comparable to prior server-side duplication timings.",'',
'## Limits and current state','',
'- Uses only ten anonymized source records. Independently compressing each record avoids exploiting duplicates across records, but field variability and document structure still affect the compression ratio. Realistic data is needed before committing to production capacity.',
'- Earlier Redis JSON results may benefit from repeated-string reuse across records. Those values are retained here as measured, not assumed to generalize.',
'- The LZ4 pre-load snapshot had zero keys but still reported memory from asynchronous deletion of the former JSON dataset. That baseline was not settled and is excluded from subtraction. The full reading was taken after the 23-minute load; a later reading confirms stability.',
'- INFO memory is the database-usage source. Redis Cloud exposes limited fields; these are not Cloud console screenshots or an assertion about host RAM.',
'- Previous JSON data was explicitly cleared, the empty database verified, then 1.6 million compressed Strings loaded. Compressed Strings remain in the database; public access remains restricted to the laptop IP and VPC.',
'- No replicas, persistence, TTLs or indexes were added. The 25 GB capacity was unchanged.','',
'Raw results: [LZ4 report](lz4_report.json), [empty snapshot](lz4_empty.json), [full snapshot](lz4_full.json), [earlier report](report.json).',
'Loader: `../compressed.py`; Lua: `../store_compressed.lua`.','']
(root/'compression-comparison.md').write_text('\n'.join(lines))
(root/'compression-projections.json').write_text(json.dumps({'method':'linear scaling of full observed used_memory','measured_bytes':used,'projections':projections},indent=2))
print(json.dumps({'used_memory':used,'projected':projections},indent=2))
