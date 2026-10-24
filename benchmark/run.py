"""Two-pass, reproducible Redis String vs JSON memory benchmark."""
import argparse, hashlib, json, os, pathlib, subprocess, time, uuid
from datetime import datetime, timezone
import redis

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / 'results'
OUT.mkdir(exist_ok=True)
TOTAL = 1_600_000
NAMESPACE = uuid.UUID('bb3227ba-63e5-4cc0-988d-f0570a3c15a3')

def parse_records(path):
    text = pathlib.Path(path).read_text()
    decoder = json.JSONDecoder(); records = []; offset = 0
    while offset < len(text):
        while offset < len(text) and text[offset].isspace(): offset += 1
        if offset == len(text): break
        value, offset = decoder.raw_decode(text, offset)
        assert isinstance(value, dict) and 'uuid' not in value
        records.append(value)
    assert len(records) == 10, f'Expected 10 records, got {len(records)}'
    return records

def key_for(i):
    return 'story:' + str(uuid.uuid5(NAMESPACE, str(i)))

def safe(command):
    try: return command()
    except redis.ResponseError as exc: return {'unsupported': str(exc)}

def snapshot(client, label):
    memory = client.info('memory')
    value = {'timestamp': datetime.now(timezone.utc).isoformat(), 'label': label,
             'dbsize': client.dbsize(), 'memory': memory,
             'stats': client.info('stats'), 'keyspace': client.info('keyspace'),
             'memory_stats': safe(lambda: client.execute_command('MEMORY', 'STATS'))}
    (OUT / f'{label}.json').write_text(json.dumps(value, indent=2))
    return value

def settle(client):
    time.sleep(10)
    deadline = time.monotonic() + 120
    while client.info('memory').get('lazyfree_pending_objects', 0):
        if time.monotonic() > deadline: raise RuntimeError('Lazy-free did not complete')
        time.sleep(2)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('sample'); args = ap.parse_args()
    records = parse_records(args.sample)
    compact = [json.dumps(r, separators=(',', ':'), ensure_ascii=False) for r in records]
    outputs = json.loads(subprocess.check_output(['terraform', 'output', '-json'], cwd=ROOT.parent))
    host, port = outputs['public_endpoint']['value'].rsplit(':', 1)
    c = redis.Redis(host=host, port=int(port), password=outputs['database_password']['value'],
                    decode_responses=True, socket_connect_timeout=10, socket_timeout=60,
                    health_check_interval=30)
    assert c.ping()
    assert c.dbsize() == 0, 'Database is not empty; refusing to mix benchmark with existing data'
    # One key per invocation: distributed naturally across shards without cross-slot Lua.
    # Literal concatenation preserves nulls, arrays and numeric representations in source.
    scripts = []
    for row in compact:
        assert ']=]' not in row
        source = '''local original = [=[%s]=]
local id = string.sub(KEYS[1], 7)
local document = '{"uuid":"' .. id .. '",' .. string.sub(original, 2)
if ARGV[1] == 'string' then
  return redis.call('SET', KEYS[1], document)
elseif ARGV[1] == 'json' then
  return redis.call('JSON.SET', KEYS[1], '$', document)
end
return redis.error_reply('Invalid storage mode')
''' % row
        scripts.append(source)
    (ROOT / 'sample.json').write_text(json.dumps(records, indent=2))
    # Generated scripts embed the supplied data; keep them with private results.
    for i, source in enumerate(scripts): (OUT / f'load_record_{i+1}.lua').write_text(source)
    shas = [c.script_load(source) for source in scripts]
    # Verify JSON availability before starting the full String pass.
    c.evalsha(shas[0], 1, key_for(0), 'json')
    assert json.loads(c.execute_command('JSON.GET', key_for(0)))['uuid'] == key_for(0)[6:]
    c.delete(key_for(0))
    settle(c)
    report = {'records': len(records), 'total_entries': TOTAL, 'namespace': str(NAMESPACE),
              'source_sha256': hashlib.sha256(pathlib.Path(args.sample).read_bytes()).hexdigest(),
              'compact_source_bytes': [len(x.encode()) for x in compact],
              'logical_payload_bytes': sum(len(x.encode()) + 46 for x in compact) * (TOTAL // 10),
              'server': c.info('server'), 'modules': safe(lambda: c.execute_command('MODULE', 'LIST')),
              'runs': {}}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2))
    for mode in ['string', 'json']:
        assert c.dbsize() == 0
        before = snapshot(c, f'{mode}_empty')
        started = time.monotonic()
        for start in range(0, TOTAL, 2000):
            keys = [key_for(i) for i in range(start, min(start+2000, TOTAL))]
            def batch():
                pipe = c.pipeline(transaction=False)
                for j, key in enumerate(keys): pipe.evalsha(shas[(start+j) % 10], 1, key, mode)
                return pipe.execute()
            try: responses = batch()
            except redis.exceptions.NoScriptError:
                shas = [c.script_load(source) for source in scripts]
                responses = batch()  # Same keys and values: retry is idempotent.
            assert all(response == 'OK' for response in responses)
            done = start + len(keys)
            if done % 100_000 == 0:
                progress = snapshot(c, f'{mode}_{done}')
                assert progress['dbsize'] == done, 'Unexpected key count / eviction'
                assert progress['stats'].get('evicted_keys', 0) == before['stats'].get('evicted_keys', 0)
                print(json.dumps({'mode':mode, 'entries':done,
                    'used_memory':progress['memory'].get('used_memory'),
                    'elapsed_seconds':round(time.monotonic()-started, 1)}), flush=True)
        load_seconds = time.monotonic()-started
        settle(c)
        after = snapshot(c, f'{mode}_full')
        assert after['dbsize'] == TOTAL
        for i in range(10):
            key = key_for(i)
            value = c.get(key) if mode == 'string' else c.execute_command('JSON.GET', key)
            expected = dict(records[i]); expected['uuid'] = key[6:]
            assert json.loads(value) == expected
        # Stratified sample spanning 100 groups and all 10 record types.
        indices = [group * (TOTAL // 100) + row for group in range(100) for row in range(10)]
        pipe = c.pipeline(transaction=False)
        for index in indices:
            pipe.memory_usage(key_for(index), samples=0)
            if mode == 'json': pipe.execute_command('JSON.DEBUG', 'MEMORY', key_for(index))
        values = iter(pipe.execute(raise_on_error=False))
        samples = []
        for index in indices:
            value = next(values)
            entry = {'index': index, 'record': index % 10 + 1,
                     'memory_usage_bytes': str(value) if isinstance(value, Exception) else value}
            if mode == 'json':
                value = next(values)
                entry['json_debug_memory_bytes'] = str(value) if isinstance(value, Exception) else value
            samples.append(entry)
        (OUT / f'{mode}_key_samples.json').write_text(json.dumps(samples, indent=2))
        report['runs'][mode] = {'load_seconds':load_seconds, 'before':before, 'after':after,
                              'key_samples_file':f'{mode}_key_samples.json'}
        (OUT / 'report.json').write_text(json.dumps(report, indent=2))
        print(f'{mode}: completed and measured {TOTAL} entries', flush=True)
        if mode == 'string':
            # User explicitly requested emptying the database between the two passes.
            assert c.dbsize() == TOTAL
            c.flushdb(asynchronous=True)
            settle(c)
            assert c.dbsize() == 0
            print('String dataset cleared; database empty.', flush=True)
    print('DONE: JSON dataset retained; report saved.', flush=True)

if __name__ == '__main__': main()
