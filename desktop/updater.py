"""Signed release manifests, bounded HTTPS downloads and SHA-256 verification."""
import base64,hashlib,json,re,urllib.request
from pathlib import Path
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import padding
from update_key import PUBLIC_KEY

VERSION='0.4.0'
MANIFEST='https://github.com/krekerhihle/orbit-display/releases/latest/download/update.json'
PREFIX='https://github.com/krekerhihle/orbit-display/releases/download/'

def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d+\.\d+\.\d+',value):raise ValueError('Invalid release version')
    return tuple(map(int,value.split('.')))

def verify_manifest(raw):
    envelope=json.loads(raw)
    payload=base64.b64decode(envelope['payload'],validate=True)
    signature=base64.b64decode(envelope['signature'],validate=True)
    key=serialization.load_der_public_key(base64.b64decode(PUBLIC_KEY))
    key.verify(signature,payload,padding.PKCS1v15(),hashes.SHA256())
    return json.loads(payload)

def check_and_download(directory):
    request=urllib.request.Request(MANIFEST,headers={'User-Agent':'Orbit-Display/'+VERSION})
    with urllib.request.urlopen(request,timeout=15) as response:
        if not response.geturl().startswith('https://'):raise ValueError('HTTPS required')
        raw=response.read(65537)
        if len(raw)>65536:raise ValueError('Manifest too large')
        manifest=verify_manifest(raw)
    item=manifest['windows']
    if version(item['version'])<=version(VERSION):return None
    if not item['url'].startswith(PREFIX) or not re.fullmatch('[0-9a-f]{64}',item['sha256']):raise ValueError('Invalid update location')
    size=item['size']
    if type(size)!=int or not 1<=size<=500*1024*1024:raise ValueError('Invalid update size')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    final=directory/('Orbit-'+item['version']+'-Setup.exe');partial=final.with_suffix('.part')
    digest=hashlib.sha256();count=0
    try:
        with urllib.request.urlopen(item['url'],timeout=30) as response,partial.open('wb') as out:
            if not response.geturl().startswith('https://'):raise ValueError('HTTPS required')
            while chunk:=response.read(262144):
                count+=len(chunk)
                if count>size:raise ValueError('Update is too large')
                out.write(chunk);digest.update(chunk)
        if count!=size or digest.hexdigest()!=item['sha256']:raise ValueError('Update checksum mismatch')
        partial.replace(final)
        return final
    finally:
        partial.unlink(missing_ok=True)
