"""Create update.json for already-built artifacts. Never publishes the private key."""
import argparse,base64,hashlib,json
from pathlib import Path
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding

p=argparse.ArgumentParser()
p.add_argument('--key',type=Path,required=True)
p.add_argument('--directory',type=Path,required=True)
p.add_argument('--version',required=True)
p.add_argument('--android-code',type=int,required=True)
a=p.parse_args()
payload={}
for platform,suffix in [('windows','Setup.exe'),('android','Android.apk')]:
    filename=f'Orbit-Display-{a.version}-{suffix}'
    path=a.directory/filename
    payload[platform]={'version':a.version,'size':path.stat().st_size,
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'url':f'https://github.com/krekerhihle/orbit-display/releases/download/v{a.version}/{filename}'}
payload['android']['versionCode']=a.android_code
raw=json.dumps(payload,separators=(',',':')).encode()
key=serialization.load_pem_private_key(a.key.read_bytes(),password=None)
signature=key.sign(raw,padding.PKCS1v15(),hashes.SHA256())
envelope={'payload':base64.b64encode(raw).decode(),'signature':base64.b64encode(signature).decode()}
(a.directory/'update.json').write_text(json.dumps(envelope,indent=2),encoding='utf-8')
print('Signed update.json for',a.version)
