"""Replace the demo dataset with 1.6M individually LZ4-compressed Strings."""
import argparse, hashlib, json, pathlib, subprocess, time
import redis, lz4, lz4.frame
import run as common

def main():
    ap=argparse.ArgumentParser();ap.add_argument('sample');ap.add_argument('--wipe',action='store_true',required=True);args=ap.parse_args()
    rows=common.parse_records(args.sample)
    bodies=[json.dumps(row,separators=(',',':'),ensure_ascii=False).encode() for row in rows]
    old=json.loads((common.OUT/'report.json').read_text())
    assert hashlib.sha256(pathlib.Path(args.sample).read_bytes()).hexdigest()==old['source_sha256']
    config=json.loads(subprocess.check_output(['terraform','output','-json'],cwd=common.ROOT.parent))
    assert str(config['database_id']['value'])=='14714560'
    host,port=config['public_endpoint']['value'].rsplit(':',1)
    c=redis.Redis(host=host,port=int(port),password=config['database_password']['value'],socket_connect_timeout=10,socket_timeout=60)
    def document(i):
        key=common.key_for(i)
        return key,b'{"uuid":"'+key[6:].encode()+b'",'+bodies[i%10][1:]
    # Check codec before the authorized destructive operation.
    for i in range(10):
        _,raw=document(i)
        assert lz4.frame.decompress(lz4.frame.compress(raw,compression_level=0))==raw
    common.snapshot(c,'lz4_pre_wipe')
    print('Clearing database 14714560.',flush=True)
    c.flushdb(asynchronous=True);common.settle(c);assert c.dbsize()==0
    previous=None;stable=0;deadline=time.monotonic()+300
    while stable < 5:
        current=c.info('memory')['used_memory']
        stable = stable+1 if previous is not None and abs(current-previous)<1_000_000 else 0
        if time.monotonic()>deadline:raise RuntimeError('Post-wipe memory did not stabilize')
        previous=current;time.sleep(5)
    lua="return redis.call('SET', KEYS[1], ARGV[1])\n"
    (common.ROOT/'store_compressed.lua').write_text(lua)
    script=c.register_script(lua)
    # Prime the script cache before measuring the empty baseline.
    sha=c.script_load(lua)
    before=common.snapshot(c,'lz4_empty')
    compressed_bytes=0;raw_bytes=0;started=time.monotonic();compression_seconds=0
    for start in range(0,common.TOTAL,2000):
        batch=[]
        for i in range(start,min(start+2000,common.TOTAL)):
            key,raw=document(i)
            tick=time.perf_counter()
            packed=lz4.frame.compress(raw,compression_level=0)
            compression_seconds+=time.perf_counter()-tick
            compressed_bytes+=len(packed);raw_bytes+=len(raw)
            batch.append((key,packed))
        pipe=c.pipeline(transaction=False)
        for key,packed in batch:script(keys=[key],args=[packed],client=pipe)
        assert all(x==b'OK' for x in pipe.execute())
        done=start+len(batch)
        if done%100_000==0:
            snap=common.snapshot(c,f'lz4_{done}')
            assert snap['dbsize']==done
            assert snap['stats'].get('evicted_keys',0)==before['stats'].get('evicted_keys',0)
            print(json.dumps({'entries':done,'used_memory':snap['memory']['used_memory'],'elapsed_seconds':round(time.monotonic()-started,1)}),flush=True)
    load_seconds=time.monotonic()-started
    common.settle(c)
    after=common.snapshot(c,'lz4_full')
    assert after['dbsize']==common.TOTAL
    indices=[g*(common.TOTAL//100)+r for g in range(100) for r in range(10)]
    pipe=c.pipeline(transaction=False)
    for i in indices:
        key=common.key_for(i);pipe.get(key);pipe.memory_usage(key,samples=0);pipe.type(key)
    results=iter(pipe.execute());samples=[]
    for i in indices:
        packed=next(results);memory=next(results);kind=next(results)
        key,raw=document(i)
        assert kind==b'string' and lz4.frame.decompress(packed)==raw
        expected=dict(rows[i%10]);expected['uuid']=key[6:]
        assert json.loads(lz4.frame.decompress(packed))==expected
        samples.append({'index':i,'record':i%10+1,'compressed_bytes':len(packed),'memory_usage_bytes':memory})
    report={'codec':'LZ4 frame','compression_level':0,'python_lz4_version':lz4.__version__,
        'total_entries':common.TOTAL,'source_sha256':old['source_sha256'],'namespace':str(common.NAMESPACE),
        'uncompressed_value_bytes':raw_bytes,'compressed_value_bytes':compressed_bytes,
        'compression_seconds':compression_seconds,'load_seconds':load_seconds,
        'before':before,'after':after,'verified_roundtrips':len(samples),'samples':samples}
    (common.OUT/'lz4_report.json').write_text(json.dumps(report,indent=2))
    assert raw_bytes==old['logical_payload_bytes']
    print('DONE: 1.6M LZ4 Strings retained, 1,000 decompression checks passed.',flush=True)

if __name__=='__main__':main()
