import base64, hashlib, io, json
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.exceptions import InvalidSignature
import updater

@pytest.fixture
def signed(monkeypatch):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    monkeypatch.setattr(updater,'PUBLIC_KEY',base64.b64encode(key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)))
    def sign(payload):
        raw=json.dumps(payload).encode()
        return json.dumps({'payload':base64.b64encode(raw).decode(),'signature':base64.b64encode(key.sign(raw,padding.PKCS1v15(),hashes.SHA256())).decode()}).encode()
    return sign

def test_signature_rejects_changed_payload(signed):
    valid=signed({'windows':{'version':'0.5.0'}})
    assert updater.verify_manifest(valid)['windows']['version']=='0.5.0'
    tampered=json.loads(valid);tampered['payload']=base64.b64encode(b'{}').decode()
    with pytest.raises(InvalidSignature):updater.verify_manifest(json.dumps(tampered))

class Response(io.BytesIO):
    def geturl(self):return 'https://release-assets.githubusercontent.com/asset'

@pytest.mark.parametrize('fault',['none','hash','size','large','location','old'])
def test_download_verified_and_partial_removed(tmp_path,monkeypatch,signed,fault):
    data=b'example installer fixture'
    item={'version':'0.5.0','url':updater.PREFIX+'v0.5.0/Orbit.exe','size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    if fault=='hash':item['sha256']='0'*64
    if fault=='size':item['size']+=1
    if fault=='large':item['size']-=1
    if fault=='location':item['url']='https://example.com/file'
    if fault=='old':item['version']='0.3.0'
    responses=iter([signed({'windows':item}),data])
    monkeypatch.setattr(updater.urllib.request,'urlopen',lambda *a,**k:Response(next(responses)))
    if fault in ('none','old'):
        result=updater.check_and_download(tmp_path)
        if fault=='none':assert result.read_bytes()==data
        else:assert result is None
    else:
        with pytest.raises(ValueError):updater.check_and_download(tmp_path)
        assert not list(tmp_path.iterdir())

def test_manifest_size_limit(tmp_path,monkeypatch):
    monkeypatch.setattr(updater.urllib.request,'urlopen',lambda *a,**k:Response(b'x'*65537))
    with pytest.raises(ValueError,match='too large'):updater.check_and_download(tmp_path)
