# String vs Redis JSON benchmark

Run from the project directory:

```sh
.venv/bin/python benchmark/run.py '/path/to/sample.txt'
```

Reads the Terraform-managed public endpoint and password in memory. Requires an empty database, Redis JSON, and the `redis` Python package. The sample consists of ten consecutive JSON objects (not a JSON array or one object per line).

Each source object is repeated 160,000 times. Stable UUIDv5 identifiers are derived from a fixed namespace and row index, and used both in `story:<uuid>` keys and the `uuid` field. Both storage modes use identical identifiers and document content. Whitespace is compacted before loading; nulls, arrays and numeric tokens are preserved during Lua duplication. Each Lua invocation writes one supplied key; pipelining avoids round trips per key and avoids a long blocking multi-million-key Lua call. Generated Lua scripts contain the sample and are saved under private `results/`.

The sequence is String load → measure → FLUSHDB ASYNC → verify empty and wait for lazy freeing → JSON load → measure. The JSON dataset is retained. Running the script again against that nonempty database intentionally fails before writing.

Measurements include:

- Exact DBSIZE and unchanged eviction count at each 100,000-key checkpoint.
- INFO memory, stats and keyspace; MEMORY STATS where supported.
- Empty baseline and settled full-database readings for each pass.
- MEMORY USAGE SAMPLES 0 for a stratified sample of 1,000 keys (100 per source row).
- JSON.DEBUG MEMORY for the JSON samples, with caveats below.
- Semantic content verification for all ten source patterns after each pass.

Redis Cloud exposes a subset of INFO fields. Report only fields actually available. Database usage means server-reported `used_memory`; it is distinct from serialized payload bytes and per-key memory estimates. The configured database capacity is 25 GB; replication, persistence, TTLs and search indexes are absent in this experiment.

This is a repeated-content memory experiment, not a production sizing or throughput benchmark. Redis JSON can reuse field names and string values across documents on the same node. MEMORY USAGE and JSON.DEBUG MEMORY must not be summed as authoritative database totals when shared strings are involved. Redis documents that JSON.DEBUG MEMORY counts repeated strings independently: https://redis.io/docs/latest/develop/data-types/json/ram/

Private raw results, progress snapshots and sample data are excluded from Git. Credentials are never written to the benchmark results.

## LZ4 compressed String pass

```sh
.venv/bin/python benchmark/compressed.py '/path/to/sample.txt' --wipe
```

This explicitly wipes database 14714560 and loads 1,600,000 Redis Strings. Each complete compact JSON document, including its UUID, is independently compressed on the laptop with `lz4.frame.compress(..., compression_level=0)`. Standard LZ4 frame headers are retained. There is no Base64 encoding, shared dictionary or compression across entries. A short Lua script stores the supplied binary bytes. Redis treats the value as opaque data; clients must decompress it before reading fields.

The run preserves the original benchmark results, records a separate empty baseline and full memory snapshot, and verifies 1,000 sampled decompression round trips and String types. Results are saved in `results/lz4_report.json`. The compressed dataset remains afterward. End-to-end load time includes uploading all compressed values from the laptop and is not directly comparable to the earlier server-side duplication runs.

Codec references: https://lz4.org/ and https://python-lz4.readthedocs.io/en/stable/lz4.frame.html
