import subprocess,json,pathlib,urllib.request
root=pathlib.Path(__file__).resolve().parent
state=root/'private/aws-resources.json'
def aws(*args):return json.loads(subprocess.check_output(['aws','--region','us-west-2',*args,'--output','json']))
tags=[{'Key':'owner','Value':'lionel_giavelli'},{'Key':'skip_deletion','Value':'yes'},{'Key':'Name','Value':'redis-flex-benchmark'}]
r=json.loads(state.read_text()) if state.exists() else {}
def save():state.write_text(json.dumps(r,indent=2))
if 'key_pair' not in r:
 x=aws('ec2','import-key-pair','--key-name','redis-flex-benchmark-lionel','--public-key-material','fileb://'+str(root/'private/benchmark-key.pub'),'--tag-specifications',json.dumps([{'ResourceType':'key-pair','Tags':tags}]))
 r['key_pair']=x['KeyName'];save()
if 'security_group' not in r:
 x=aws('ec2','create-security-group','--group-name','redis-flex-benchmark-lionel','--description','Redis Flex load and benchmark VM','--vpc-id','vpc-0bdba995c15e5371d','--tag-specifications',json.dumps([{'ResourceType':'security-group','Tags':tags}]))
 r['security_group']=x['GroupId'];save()
 ip=urllib.request.urlopen('https://checkip.amazonaws.com').read().decode().strip()
 aws('ec2','authorize-security-group-ingress','--group-id',r['security_group'],'--ip-permissions',json.dumps([{'IpProtocol':'tcp','FromPort':22,'ToPort':22,'IpRanges':[{'CidrIp':ip+'/32','Description':'Owner laptop SSH'}]}]))
if 'instance_id' not in r:
 user='''#!/bin/bash
set -eu
dnf install -y python3 python3-pip git gcc python3-devel
mkdir -p /home/ec2-user/flex-benchmark
chown ec2-user:ec2-user /home/ec2-user/flex-benchmark
sudo -u ec2-user python3 -m venv /home/ec2-user/flex-benchmark/.venv
sudo -u ec2-user /home/ec2-user/flex-benchmark/.venv/bin/pip install 'redis>=6,<8' 'lz4>=4,<5' numpy
'''
 (root/'private/user-data.sh').write_text(user)
 x=aws('ec2','run-instances','--image-id','ami-0e0fcdc77c6355731','--instance-type','c7i.4xlarge','--key-name',r['key_pair'],'--network-interfaces',json.dumps([{'DeviceIndex':0,'SubnetId':'subnet-0a5769ac32b192dad','Groups':[r['security_group']],'AssociatePublicIpAddress':True}]),'--metadata-options','HttpTokens=required,HttpEndpoint=enabled','--block-device-mappings',json.dumps([{'DeviceName':'/dev/xvda','Ebs':{'VolumeSize':40,'VolumeType':'gp3','Encrypted':True,'DeleteOnTermination':True}}]),'--tag-specifications',json.dumps([{'ResourceType':t,'Tags':tags} for t in ['instance','volume','network-interface']]),'--user-data','file://'+str(root/'private/user-data.sh'),'--client-token','redis-flex-benchmark-20261023-lionel')
 r['instance_id']=x['Instances'][0]['InstanceId'];save()
print(json.dumps(r,indent=2))
