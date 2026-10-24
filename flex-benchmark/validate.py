import argparse,json,random,lz4.frame
from common import *
p=argparse.ArgumentParser();p.add_argument('--population',type=int,required=True);args=p.parse_args()
c=client();assert c.dbsize()==args.population*2
rows=json.loads((ROOT/'sample.json').read_text())
rng=random.Random(777)
indices=list(range(10))+[rng.randrange(args.population) for _ in range(990)]
checked={}
for mode in ['plain','lz4']:
    pipe=c.pipeline(transaction=False)
    for i in indices:pipe.get(key(mode,i));pipe.type(key(mode,i))
    values=iter(pipe.execute())
    for i in indices:
        value=next(values);typ=next(values)
        assert value is not None and typ==b'string'
        if mode=='lz4':value=lz4.frame.decompress(value)
        expected=dict(rows[i%10]);expected['uuid']=uid(i)
        assert json.loads(value)==expected
    checked[mode]=len(indices)
snap=snapshot(c)
report={'population_per_format':args.population,'sample_checks_per_format':checked,'snapshot':snap}
save(ROOT/'results/validation.json',report)
print(json.dumps(report),flush=True)
