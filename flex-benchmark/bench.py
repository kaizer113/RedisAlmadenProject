"""Open-loop uniform-random private-endpoint GET benchmarks."""
import asyncio,argparse,json,time,random,os,pathlib,traceback
import numpy as np
import redis.asyncio as aredis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
import lz4.frame
from common import *

def percentiles(values):
    a=np.array(values,dtype=float)*1000
    return {k:float(np.percentile(a,p)) for k,p in [('p50_ms',50),('p95_ms',95),('p99_ms',99),('p999_ms',99.9)]}|{'max_ms':float(a.max()),'mean_ms':float(a.mean())} if len(a) else {}
def net():
    rows={}
    for line in pathlib.Path('/proc/net/dev').read_text().splitlines()[2:]:
        name,data=line.split(':');v=list(map(int,data.split()))
        if name.strip()!='lo':rows[name.strip()]={'rx_bytes':v[0],'tx_bytes':v[8]}
    return rows

def command_bytes(k):
    n=len(k.encode());return 4+4+5+len(str(n))+3+n+2

async def phase(c,mode,batch,duration,seed,record):
    rng=random.Random(seed)
    batches_per_second=2000/batch
    requests=int(duration*batches_per_second)
    pending=set();stats={'errors':0,'misses':0,'payload_bytes':0,'request_resp_bytes':0,'response_resp_bytes':0,'decoded_bytes':0}
    read_lat=[];app_lat=[];scheduled_lat=[];lag=[];errors=[];finished_by_second=[0]*(duration+120)
    semaphore=asyncio.Semaphore(256)
    start=time.perf_counter()+0.1
    net_before=net();redis_before=await c.info('stats')
    async def request(index,due,ids):
        try:
            keys=[key(mode,i) for i in ids]
            if batch>1:
                pipe=c.pipeline(transaction=False)
                for k in keys:pipe.get(k)
            async with semaphore:
                sent=time.perf_counter()
                if batch==1:values=[await c.get(keys[0])]
                else:values=await pipe.execute()
                received=time.perf_counter()
                if any(v is None for v in values):
                    stats['misses']+=sum(v is None for v in values);raise RuntimeError('Missing key in benchmark')
                if mode=='lz4':
                    decoded=[lz4.frame.decompress(v) for v in values]
                    decoded_size=sum(map(len,decoded))
                else:decoded_size=sum(map(len,values))
                finished=time.perf_counter()
                read_lat.append(received-sent);app_lat.append(finished-sent);scheduled_lat.append(finished-due);lag.append(sent-due)
                stats['payload_bytes']+=sum(map(len,values));stats['decoded_bytes']+=decoded_size
                stats['request_resp_bytes']+=sum(command_bytes(k) for k in keys)
                stats['response_resp_bytes']+=sum(len(v)+len(str(len(v)))+5 for v in values)
                bucket=int(finished-start)
                if 0<=bucket<len(finished_by_second):finished_by_second[bucket]+=batch
        except Exception as exc:
            stats['errors']+=1
            if len(errors)<10:errors.append(str(exc))
    for i in range(requests):
        due=start+i/batches_per_second
        delay=due-time.perf_counter()
        if delay>0:await asyncio.sleep(delay)
        if len(pending)>5000:raise RuntimeError('Load generator backlog exceeded 5,000 batches')
        ids=[rng.randrange(TOTAL) for _ in range(batch)]
        task=asyncio.create_task(request(i,due,ids));pending.add(task);task.add_done_callback(pending.discard)
    if pending:await asyncio.gather(*pending)
    # Keep each measured window open for the full requested duration.
    if time.perf_counter()<start+duration:await asyncio.sleep(start+duration-time.perf_counter())
    end=time.perf_counter();net_after=net();redis_after=await c.info('stats')
    actual=end-start;completed=len(read_lat);records=completed*batch
    nic={name:{field:net_after[name][field]-v[field] for field in v} for name,v in net_before.items() if name in net_after}
    result={'mode':mode,'batch_size':batch,'operation':'GET' if batch==1 else 'pipeline of independent GET commands',
        'target_records_per_second':2000,'target_batches_per_second':batches_per_second,
        'scheduled_duration_seconds':duration,'elapsed_seconds':actual,'attempted_batches':requests,
        'successful_batches':completed,'successful_records':records,'achieved_records_per_second':records/actual,
        'read_latency':percentiles(read_lat),'application_latency_including_lz4_decode':percentiles(app_lat),
        'scheduled_to_completion_latency':percentiles(scheduled_lat),'scheduling_lag':percentiles(lag),
        'record_completions_by_second':finished_by_second[:int(actual)+1],**stats,'error_examples':errors,
        'throughput':{'value_payload_MB_per_second':stats['payload_bytes']/actual/1e6,
            'value_payload_Mbit_per_second':stats['payload_bytes']*8/actual/1e6,
            'resp_request_MB_per_second':stats['request_resp_bytes']/actual/1e6,
            'resp_response_MB_per_second':stats['response_resp_bytes']/actual/1e6,
            'resp_combined_Mbit_per_second':(stats['request_resp_bytes']+stats['response_resp_bytes'])*8/actual/1e6,
            'decoded_MB_per_second':stats['decoded_bytes']/actual/1e6},
        'nic_byte_deltas':nic,'redis_stats_before':redis_before,'redis_stats_after':redis_after,
        'private_endpoint':config()['host'],'seed':seed,'uuid_scheme':PREFIX+'<12 hexadecimal digits of index>'}
    if record:
        stem=f'{mode}-batch-{batch}'
        save(ROOT/'results'/f'{stem}.json',result)
        np.savez_compressed(ROOT/'results'/f'{stem}-latencies.npz',read_seconds=read_lat,application_seconds=app_lat,scheduled_seconds=scheduled_lat,lag_seconds=lag)
    assert stats['errors']==0 and stats['misses']==0,result
    assert abs(records/actual-2000)/2000<0.01,('Achieved rate outside 1%',result)
    return result

async def main():
    global TOTAL
    ap=argparse.ArgumentParser();ap.add_argument('--duration',type=int,default=180);ap.add_argument('--warmup',type=int,default=30);ap.add_argument('--smoke',action='store_true');ap.add_argument('--population',type=int,default=140_000_000);args=ap.parse_args()
    TOTAL=args.population
    if not args.smoke:assert args.duration>=180
    c=aredis.Redis(**config(),max_connections=256,socket_connect_timeout=10,socket_timeout=30,retry=Retry(NoBackoff(),0))
    assert await c.ping()
    if not args.smoke:assert await c.dbsize()==TOTAL*2
    manifest=[]
    for batch in [1,10,100,1000]:
        for mode in ['plain','lz4']:
            resultpath=ROOT/'results'/f'{mode}-batch-{batch}.json'
            if resultpath.exists() and not args.smoke:
                saved=json.loads(resultpath.read_text())
                if saved['scheduled_duration_seconds']>=180 and saved['errors']==0 and saved['misses']==0 and abs(saved['achieved_records_per_second']-2000)/2000<0.01:
                    manifest.append(saved);continue
            print(f'WARMUP {mode} batch={batch}',flush=True)
            await phase(c,mode,batch,args.warmup,20261023+(batch-1)*100000,False)
            print(f'MEASURE {mode} batch={batch}',flush=True)
            r=await phase(c,mode,batch,args.duration,8675309+(batch-1)*100000,not args.smoke)
            print(json.dumps({k:r[k] for k in ['mode','batch_size','achieved_records_per_second','read_latency','throughput']}),flush=True)
            manifest.append(r)
            await asyncio.sleep(10)
    if not args.smoke:save(ROOT/'results/benchmark-summary.json',manifest)
    await c.aclose()
if __name__=='__main__':asyncio.run(main())
