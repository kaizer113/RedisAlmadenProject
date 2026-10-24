import argparse,json,time,pathlib,multiprocessing,traceback,redis
from common import *
BATCH=256

def worker(w,workers,tasks):
    c=client();scripts={m:c.register_script((ROOT/f'load_{m}.lua').read_text()) for m in ['plain','lz4']}
    path=ROOT/'results'/f'worker-{w:02d}.json'
    state=json.loads(path.read_text()) if path.exists() else {'next_task':w,'completed_per_dataset':0,'worker':w}
    try:
        for task in range(state['next_task'],tasks,workers):
            if (ROOT/'STOP_LOAD').exists():break
            sweep,bucket=divmod(task,BUCKETS)
            indices=[sweep*BUCKETS*BATCH+bucket+j*BUCKETS for j in range(BATCH)]
            indices=[i for i in indices if i<TOTAL]
            if not indices:continue
            # Single-slot batches: each Lua execution accesses only declared KEYS.
            for mode in ['plain','lz4']:
                result=scripts[mode](keys=[key(mode,i) for i in indices])
                assert result==len(indices),result
            state.update(next_task=task+workers,completed_per_dataset=state['completed_per_dataset']+len(indices),updated=time.time())
            save(path,state)
        state['finished']=True;save(path,state)
    except BaseException:
        state['error']=traceback.format_exc();save(path,state);raise

def main():
    global TOTAL
    p=argparse.ArgumentParser();p.add_argument('--pilot',action='store_true');p.add_argument('--pilot-sweeps',type=int,default=1);p.add_argument('--workers',type=int,default=16);p.add_argument('--records',type=int,default=140_000_000);args=p.parse_args()
    TOTAL=args.records
    (ROOT/'results').mkdir(exist_ok=True)
    c=client();manifest=ROOT/'results/load-manifest.json'
    if not manifest.exists():
        assert c.dbsize()==0,'Flex database must be empty before initial loading'
        save(manifest,{'start':time.time(),'workers':args.workers,'batch':BATCH,'total_per_dataset':TOTAL,'baseline':snapshot(c)})
    else:
        previous=json.loads(manifest.read_text());assert previous['workers']==args.workers
        previous['total_per_dataset']=TOTAL;save(manifest,previous)
    tasks=BUCKETS*args.pilot_sweeps if args.pilot else ((TOTAL+BUCKETS*BATCH-1)//(BUCKETS*BATCH))*BUCKETS
    started=time.time()
    processes=[multiprocessing.Process(target=worker,args=(w,args.workers,tasks)) for w in range(args.workers)]
    for process in processes:process.start()
    while any(x.is_alive() for x in processes):
        time.sleep(20)
        states=[json.loads(x.read_text()) for x in (ROOT/'results').glob('worker-*.json')]
        errors=[x for x in states if x.get('error')]
        snap=snapshot(c);snap['completed_per_dataset']=sum(x['completed_per_dataset'] for x in states);snap['elapsed']=time.time()-started
        save(ROOT/'results/load-current.json',snap)
        with (ROOT/'results/load-progress.jsonl').open('a') as f:f.write(json.dumps(snap)+'\n')
        print(json.dumps({'completed_per_dataset':snap['completed_per_dataset'],'keys':snap['dbsize'],'elapsed':round(snap['elapsed']),'memory':snap['memory']}),flush=True)
        # Preserve data and halt if evictions or a worker error occur.
        if errors or snap['stats'].get('evicted_keys',0)>json.loads(manifest.read_text())['baseline']['stats'].get('evicted_keys',0):
            (ROOT/'STOP_LOAD').touch()
            for process in processes:process.join(10)
            raise RuntimeError('Load stopped: worker error or eviction; inspect checkpoints')
    for process in processes:
        process.join();assert process.exitcode==0
    end=snapshot(c);save(ROOT/'results'/('pilot.json' if args.pilot else 'loaded.json'),end)
    expected=2*BUCKETS*BATCH*args.pilot_sweeps if args.pilot else 2*TOTAL
    assert end['dbsize']==expected,(end['dbsize'],expected)
    print('PILOT COMPLETE' if args.pilot else 'LOAD COMPLETE',flush=True)
if __name__=='__main__':main()
