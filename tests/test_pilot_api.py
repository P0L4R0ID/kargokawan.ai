import base64
import io
import json
import time
from urllib.error import HTTPError
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from oauth_callback import create_app
from pilot_api import configured_store
from pilot_store import OperatorVerifier, PilotStore
from pilot_client import call_pilot


def setup(tmp_path):
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    numbers=private.public_key().public_numbers()
    b64=lambda x: base64.urlsafe_b64encode(x.to_bytes((x.bit_length()+7)//8,'big')).rstrip(b'=').decode()
    jwks={'keys':[{'kid':'one','kty':'RSA','n':b64(numbers.n),'e':b64(numbers.e)}]}
    verifier=OperatorVerifier('https://issuer.example','frontend-client','allowed',jwks=jwks)
    store=PilotStore(tmp_path/'pilot.sqlite',verifier,tmp_path)
    def token(sub='allowed',**changes):
        claims={'iss':'https://issuer.example','aud':'frontend-client','sub':sub,
                'iat':int(time.time()),'exp':int(time.time())+300}
        claims.update(changes)
        return jwt.encode(claims,private,algorithm='RS256',headers={'kid':'one'})
    return create_app(pilot_store=store),token


def call(app,path,method='GET',token=None,body=None,key=None,version=None):
    data=json.dumps(body).encode() if body is not None else b''
    env={'PATH_INFO':path,'REQUEST_METHOD':method,'wsgi.input':io.BytesIO(data),
         'CONTENT_LENGTH':str(len(data)),'CONTENT_TYPE':'application/json'}
    if token:env['HTTP_AUTHORIZATION']='Bearer '+token
    if key:env['HTTP_IDEMPOTENCY_KEY']=key
    if version is not None:env['HTTP_IF_MATCH']=str(version)
    result={}
    response=b''.join(app(env,lambda status,headers:result.update(status=status,headers=dict(headers))))
    try: decoded=json.loads(response)
    except json.JSONDecodeError: decoded=response.decode()
    return int(result['status'][:3]),decoded


ORDER={'order_id':'PILOT-1','origin':'Kuala Lumpur','destination':'Kuching','weight_kg':2,
       'length_cm':20,'width_cm':10,'height_cm':5,'deadline_days':5,'recipient':'Test Recipient',
       'origin_postcode':'05000','destination_postcode':'93000'}
QUOTE={'source_class':'USER_IMPORTED_UNVERIFIED','provider':'EasyParcel Malaysia',
       'service':'Parcel','source_reference':'user document'}


def test_pilot_authentication_and_storage_gate(tmp_path):
    app,token=setup(tmp_path)
    assert call(app,'/pilot/status')[0]==401
    assert call(app,'/pilot/status',token=token('wrong'))[0]==403
    assert call(app,'/pilot/status',token=token(aud='wrong-audience'))[0]==403
    assert call(app,'/pilot/status',token=token(exp=int(time.time())-120))[0]==403
    assert call(app,'/pilot/status',token=token())[0]==200
    gated=create_app()
    assert call(gated,'/pilot/status',token=token())[0]==503
    assert configured_store({'PILOT_ENABLED':'1','PILOT_DB':'/var/data/pilot.sqlite'},mount_check=lambda path:False) is None
    env={'PILOT_ENABLED':'1','PILOT_DB':str(tmp_path/'pilot-configured.sqlite'),
         'PILOT_OIDC_ISSUER':'https://issuer.example','PILOT_OIDC_AUDIENCE':'frontend-client',
         'PILOT_OIDC_SUBJECT':'allowed','PILOT_OIDC_JWKS_URL':'https://issuer.example/keys'}
    assert configured_store(env,mount_check=lambda path:False,persistent_root=tmp_path) is None
    assert isinstance(configured_store(env,mount_check=lambda path:True,persistent_root=tmp_path),PilotStore)


def test_private_jobs_quotes_versions_and_replay(tmp_path):
    app,token=setup(tmp_path);owner=token();other=token('wrong')
    key='request-unique-123456'
    status,created=call(app,'/pilot/jobs','POST',owner,{'orders':[ORDER]},key)
    assert status==201 and created['version']==1
    job=created['job_id'];path='/pilot/jobs/'+job
    assert call(app,'/pilot/jobs','POST',owner,{'orders':[ORDER]},key)[1]['job_id']==job
    assert call(app,'/pilot/jobs','POST',owner,{'orders':[dict(ORDER,recipient='Changed')]},key)[0]==409
    assert call(app,path,token=other)[0]==403
    assert call(app,path,token=owner)[1]['orders'][0]['origin_postcode']=='05000'
    assert call(app,path,'PUT',owner,{'orders':[ORDER]},version=1)[1]['version']==2
    assert call(app,path,'PUT',owner,{'orders':[ORDER]},version=1)[0]==409
    qpath=path+'/quotes'
    status,created_quote=call(app,qpath,'POST',owner,{'quote':QUOTE},'quote-unique-123456')
    assert status==201
    quote_id=created_quote['quote_id']
    assert call(app,qpath,'POST',owner,{'quote':QUOTE},'quote-unique-123456')[1]['quote_id']==quote_id
    assert call(app,qpath+'/'+quote_id,token=owner)[1]['quote']['source_class']=='USER_IMPORTED_UNVERIFIED'
    assert call(app,qpath+'/'+quote_id,token=other)[0]==403
    assert call(app,qpath+'/'+quote_id,'PUT',owner,{'quote':dict(QUOTE,service='Express')},version=1)[1]['version']==2
    assert call(app,qpath+'/'+quote_id,'PUT',owner,{'quote':QUOTE},version=1)[0]==409
    assert call(app,path,'PUT',owner,{'orders':[ORDER]},version=2)[0]==200
    assert call(app,qpath,token=owner)[1]['quote_ids']==[]


def test_pilot_rejects_untrusted_data_and_unsafe_methods(tmp_path):
    app,token=setup(tmp_path);owner=token()
    assert call(app,'/pilot/jobs','POST',owner,{'orders':[dict(ORDER,origin_postcode='5000')]},'order-key-123456789')[0]==400
    assert call(app,'/pilot/jobs','POST',owner,{'orders':[ORDER]},None)[0]==400
    job=call(app,'/pilot/jobs','POST',owner,{'orders':[ORDER]},'order-key-123456789')[1]['job_id']
    qpath='/pilot/jobs/'+job+'/quotes'
    assert call(app,qpath,'POST',owner,{'quote':dict(QUOTE,source_class='LIVE_AUTHENTICATED')},'quote-key-123456789')[0]==400
    assert call(app,qpath,'POST',owner,{'quote':dict(QUOTE,access_token='secret')},'quote-key-123456789')[0]==400
    assert call(app,'/pilot/jobs/'+job,'DELETE',owner)[0]==404
    assert call(app,'/oauth/easyparcel/start',token=owner)[0]==403
    assert call(app,'/oauth/easyparcel/callback',token=owner)[0]==403


def test_frontend_bridge_is_server_side_and_sanitized():
    class FakeResponse:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return b'{"status":"READY","easyparcel_oauth":"NOT_CONNECTED"}'
    def transport(req):
        assert req.full_url=='https://kargokawan-oauth.onrender.com/pilot/status'
        assert req.get_header('Authorization')=='Bearer signed-id-token'
        return FakeResponse()
    result=call_pilot('signed-id-token','GET','/pilot/status',transport=transport)
    assert result['data']['easyparcel_oauth']=='NOT_CONNECTED'
    assert call_pilot('','GET','/pilot/status')['status']=='NOT_CONNECTED'


def test_frontend_bridge_hides_backend_errors_and_tokens():
    def unavailable(req):
        raise HTTPError(req.full_url,503,'secret detail',None,None)
    result=call_pilot('signed-id-token','GET','/pilot/status',transport=unavailable)
    assert result['status']=='NOT_CONNECTED'
    assert 'signed-id-token' not in str(result) and 'secret detail' not in str(result)
