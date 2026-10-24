import json,pathlib,time,redis,socket,ipaddress
ROOT=pathlib.Path(__file__).resolve().parent
BUCKETS=4096
TOTAL=140_000_000
PREFIX='b74613d0-2026-8abc-8def-'

def uid(index):return PREFIX+f'{index:012x}'
def key(mode,index):return f'{mode}:{{{index%BUCKETS:04x}}}:'+uid(index)
def config():
    x=json.loads((ROOT/'redis.json').read_text())
    assert x['database_id']==14715459
    ips=socket.gethostbyname_ex(x['host'])[2]
    assert all(ipaddress.ip_address(i) in ipaddress.ip_network('192.168.1.0/24') for i in ips),ips
    return {k:x[k] for k in ['host','port','password']}
def client():return redis.Redis(**config(),socket_connect_timeout=10,socket_timeout=120,health_check_interval=30)
def snapshot(c):
    return {'timestamp':time.time(),'dbsize':c.dbsize(),'memory':c.info('memory'),'stats':c.info('stats'),'keyspace':c.info('keyspace')}
def save(path,data):
    p=pathlib.Path(path);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2));tmp.replace(p)
