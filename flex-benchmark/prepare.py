import sys,json,pathlib,struct,lz4.frame,lz4.block,uuid,argparse
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'benchmark'))
from run import parse_records
sys.path.insert(0,str(ROOT));from common import uid
parser=argparse.ArgumentParser(description='Generate Lua loaders from ten consecutive JSON objects.')
parser.add_argument('sample',help='Path to the private source sample')
args=parser.parse_args()
(ROOT/'private').mkdir(exist_ok=True)
rows=parse_records(args.sample)
raw=[json.dumps(r,separators=(',',':'),ensure_ascii=False).encode() for r in rows]
ctx=lz4.frame.create_compression_context()
header=lz4.frame.compress_begin(ctx,block_linked=False,compression_level=0,auto_flush=True,source_size=0)
# Standard independent-block LZ4 frame. UUID prefix is a literal block;
# the rest of the JSON is an independently compressed block, with no shared dictionary.
frame_head=header+struct.pack('<I',0x80000000|47)
compressed=[lz4.block.compress(r[1:],store_size=False) for r in raw]
frame_tails=[struct.pack('<I',len(x))+x+b'\0\0\0\0' for x in compressed]
def lua_bytes(b):return '"'+''.join('\\%03d'%x for x in b)+'"'
for mode in ['plain','lz4']:
    items=[r[1:] for r in raw] if mode=='plain' else frame_tails
    source='local templates = {'+','.join(lua_bytes(x) for x in items)+'}\n'
    if mode=='lz4':source+='local header = '+lua_bytes(frame_head)+'\n'
    source+='''for _, key in ipairs(KEYS) do
  local id = string.sub(key, -36)
  local index = tonumber(string.sub(id, -12), 16)
  local prefix = '{"uuid":"' .. id .. '",'
  local body = templates[index % 10 + 1]
'''
    source+="  redis.call('SET', key, "+('header .. prefix .. body' if mode=='lz4' else 'prefix .. body')+")\nend\nreturn #KEYS\n"
    (ROOT/f'load_{mode}.lua').write_text(source)
for i in [*range(10),139999999]:
    ident=uid(i);assert uuid.UUID(ident).version==8
    prefix=b'{"uuid":"'+ident.encode()+b'",'
    assert len(prefix)==47
    decoded=lz4.frame.decompress(frame_head+prefix+frame_tails[i%10])
    assert decoded==prefix+raw[i%10][1:]
(ROOT/'private/sample.json').write_text(json.dumps(rows))
(ROOT/'codec-manifest.json').write_text(json.dumps({'codec':'standard LZ4 frame, independent blocks','uuid':'deterministic UUIDv8 with 48-bit record index','plain_value_sizes':[len(x)+46 for x in raw],'lz4_value_sizes':[len(frame_head)+47+len(x) for x in frame_tails],'total_per_dataset':140000000,'bucket_count':4096},indent=2))
print('Both Lua loaders generated; standard LZ4 decoder verified for all source patterns.')
