"""Fetch a known record by index using the private endpoint."""
import argparse,json,lz4.frame
from common import *
p=argparse.ArgumentParser();p.add_argument('mode',choices=['plain','lz4']);p.add_argument('index',type=int);args=p.parse_args()
assert 0<=args.index<TOTAL
k=key(args.mode,args.index);value=client().get(k)
if value is None:raise RuntimeError('Expected key is missing: '+k)
if args.mode=='lz4':value=lz4.frame.decompress(value)
print(json.dumps({'key':k,'document':json.loads(value)},indent=2))
