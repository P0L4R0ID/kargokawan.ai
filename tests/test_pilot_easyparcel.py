"""Mock provider calls; PostgreSQL tests use a disposable local database."""
import base64
import io
import json
import time
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
import pytest

from oauth_callback import create_app
from pilot_easyparcel import (BACKEND_ORIGIN, CALLBACK, PilotEasyParcelService,
                              configuration, SAMPLE_ORDER, SAMPLE_CODES)
from easyparcel_openapi import STANDARD_URL, standard_payload
from tests.test_postgres_pilot_store import pg_store, identity


def call(app, path, method='GET', identity_token=None, body=None, cookie='', host='kargokawan-oauth.onrender.com'):
    url = urlsplit(path)
    data = json.dumps(body).encode() if body is not None else b''
    environ = {'PATH_INFO':url.path,'QUERY_STRING':url.query,'REQUEST_METHOD':method,
               'HTTP_HOST':host,'HTTP_COOKIE':cookie,'wsgi.input':io.BytesIO(data),
               'CONTENT_LENGTH':str(len(data)),'CONTENT_TYPE':'application/json',
               'HTTP_IDEMPOTENCY_KEY':'fictional-test-request-key-12345'}
    if identity_token: environ['HTTP_AUTHORIZATION']='Bearer '+identity_token
    captured={}
    raw=b''.join(app(environ,lambda status,headers:captured.update(status=status,headers=dict(headers))))
    try: value=json.loads(raw)
    except (ValueError,UnicodeError): value=raw.decode()
    return int(captured['status'][:3]),captured['headers'],value


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self,*args): self.close()


def test_configuration_is_disabled_and_exact_callback_only():
    key=Fernet.generate_key().decode()
    env={'EASYPARCEL_OAUTH_CLIENT_ID':'fictional-client',
         'EASYPARCEL_OAUTH_CLIENT_SECRET':'fictional-secret',
         'EASYPARCEL_OAUTH_FERNET_KEY':key,
         'EASYPARCEL_OAUTH_REDIRECT_URI':CALLBACK}
    assert configuration(env) is None
    env['EASYPARCEL_OAUTH_ENABLED']='1'
    assert configuration(env)['EASYPARCEL_OAUTH_REDIRECT_URI']==CALLBACK
    env['EASYPARCEL_OAUTH_REDIRECT_URI']=CALLBACK+'/extra'
    assert configuration(env) is None


def test_owner_bound_oauth_hosts_replay_encryption_and_sample(pg_store, identity):
    owner=identity[1]()
    wrong=identity[1]('wrong')
    with pg_store.pool.connection() as db:
        db.execute('DELETE FROM pilot_easyparcel_rate_checks WHERE owner_sub=%s', ('allowed',))
        db.execute('DELETE FROM pilot_easyparcel_tokens WHERE owner_sub=%s', ('allowed',))
    now=[int(time.time())]
    env={'EASYPARCEL_OAUTH_ENABLED':'1',
         'EASYPARCEL_OAUTH_CLIENT_ID':'fictional-client',
         'EASYPARCEL_OAUTH_CLIENT_SECRET':'fictional-secret',
         'EASYPARCEL_OAUTH_FERNET_KEY':Fernet.generate_key().decode(),
         'EASYPARCEL_OAUTH_REDIRECT_URI':CALLBACK}
    config=configuration(env)
    token_calls=[];quote_calls=[];environment_evidence=[None]

    def token_transport(req):
        token_calls.append(req)
        assert req.full_url=='https://api.easyparcel.com/oauth/token'
        assert req.get_header('Authorization')=='Basic '+base64.b64encode(
            b'fictional-client:fictional-secret').decode()
        return Response(json.dumps({'token_type':'Bearer','access_token':'fictional-access',
            'refresh_token':'fictional-refresh','expires_in':36000,
            'refresh_token_expires_in':31557600}).encode())

    def quote_transport(req,timeout):
        quote_calls.append(req)
        assert req.full_url==STANDARD_URL and req.get_method()=='POST' and timeout==12
        assert req.get_header('Authorization')=='Bearer fictional-access'
        shipment=standard_payload([SAMPLE_ORDER],SAMPLE_CODES)['shipment'][0]
        assert json.loads(req.data)=={'shipment':[shipment]}
        return Response(json.dumps({'status_code':200,'request_id':'fictional-provider-request',
            'rate_limit':{'limit_set':environment_evidence[0]},
            'data':[{'status':'success','input':shipment,'quotations':[{
                'courier':{'courier_id':'TEST','courier_name':'Fictional test courier',
                    'service_id':'TEST-SERVICE','service_name':'Fictional test service',
                    'delivery_duration':None},
                'pricing':{'currency':'MYR','total_amount':'12.31',
                           'seller_payable_amount':'12.31'}}]}]}).encode())

    service=PilotEasyParcelService(pg_store,config,transport=quote_transport,
                                   token_transport=token_transport,clock=lambda:now[0])
    app=create_app(env,token_transport,clock=lambda:now[0],
                   pilot_store=pg_store,easyparcel_service=service)
    status,_,_=call(app,'/pilot/easyparcel/link-intent','POST',None,{'authorization_host':'api'})
    assert status==401
    status,_,_=call(app,'/pilot/easyparcel/link-intent','POST',wrong,{'authorization_host':'api'})
    assert status==403
    status,_,prepared=call(app,'/pilot/easyparcel/link-intent','POST',owner,{'authorization_host':'api'})
    assert status==200 and prepared['start_url'].startswith(BACKEND_ORIGIN+'/oauth/easyparcel/start?ticket=')
    assert call(app,prepared['start_url'],host='attacker.example')[0]==400
    status,headers,_=call(app,prepared['start_url'])
    assert status==302 and headers['Location'].startswith('https://api.easyparcel.com/oauth/login?')
    assert 'Secure' in headers['Set-Cookie'] and 'HttpOnly' in headers['Set-Cookie']
    state=parse_qs(urlsplit(headers['Location']).query)['state'][0]
    cookie=headers['Set-Cookie'].split(';')[0]
    assert call(app,prepared['start_url'])[0]==400
    callback='/oauth/easyparcel/callback?code=fictional-code&state='+state
    assert call(app,callback,cookie='wrong=cookie')[0]==400
    assert call(app,callback,cookie=cookie)[0]==200
    assert call(app,callback,cookie=cookie)[0]==400
    assert len(token_calls)==1
    with pg_store.pool.connection() as db:
        ciphertext=db.execute('SELECT ciphertext FROM pilot_easyparcel_tokens WHERE owner_sub=%s',
                              ('allowed',)).fetchone()[0]
    assert b'fictional-access' not in bytes(ciphertext)
    with pytest.raises(ValueError,match='connection changed'):
        pg_store.easyparcel_save_tokens('allowed',b'encrypted-test-only',now[0]+36000,
            now[0]+31557600,now=now[0],expected_ciphertext=b'outdated-ciphertext')
    assert call(app,'/pilot/easyparcel/connection',identity_token=wrong)[0]==403
    status,_,connection=call(app,'/pilot/easyparcel/connection',identity_token=owner)
    assert status==200 and connection['environment']=='UNKNOWN'
    status,_,observed=call(app,'/pilot/easyparcel/sandbox-quotation','POST',owner,{})
    assert status==200 and observed['environment']=='UNKNOWN'
    assert observed['observations'][0]['delivery_duration'] is None
    assert observed['observations'][0]['planner_eligible'] is False
    assert len(quote_calls)==1
    assert call(app,'/pilot/easyparcel/sandbox-quotation','POST',wrong,{})[0]==403
    assert call(app,'/pilot/easyparcel/sandbox-quotation','POST',owner,{})[0]==400
    assert len(quote_calls)==1
    now[0]+=31
    environment_evidence[0]='sandbox'
    status,_,observed=call(app,'/pilot/easyparcel/sandbox-quotation','POST',owner,{})
    assert status==200 and observed['environment']=='Sandbox'
    assert call(app,'/pilot/easyparcel/connection',identity_token=owner)[2]['environment']=='Sandbox'
    now[0]+=35920
    status,_,observed=call(app,'/pilot/easyparcel/sandbox-quotation','POST',owner,{})
    assert status==200 and observed['environment']=='Sandbox'
    assert any(b'grant_type=refresh_token' in request.data for request in token_calls)
    assert call(app,'/pilot/easyparcel/connection',identity_token=owner)[2]['environment']=='Sandbox'
    now[0]+=31
    environment_evidence[0]='live'
    assert call(app,'/pilot/easyparcel/sandbox-quotation','POST',owner,{})[2]['environment']=='Live'
    assert call(app,'/pilot/easyparcel/sandbox-quotation','POST',owner,{})[0]==400
    now[0]=int(time.time())
    status,_,fresh=call(app,'/pilot/easyparcel/link-intent','POST',owner,{'authorization_host':'developer'})
    status,headers,_=call(app,fresh['start_url'])
    assert status==302 and headers['Location'].startswith('https://developer.easyparcel.com/oauth/login?')


def test_store_state_cookie_and_owner_isolation(pg_store, identity):
    owner=identity[1]()
    ticket=pg_store.easyparcel_link_ticket(owner,'api',now=100)
    assert pg_store.easyparcel_begin_link(ticket,'state-a','cookie-a',now=101)=='api'
    try:
        pg_store.easyparcel_begin_link(ticket,'state-b','cookie-b',now=101)
        assert False, 'ticket replay was accepted'
    except PermissionError: pass
    try:
        pg_store.easyparcel_consume_state('state-a','cookie-b',now=102)
        assert False, 'wrong cookie was accepted'
    except PermissionError: pass
    assert pg_store.easyparcel_consume_state('state-a','cookie-a',now=102)=='allowed'
    try:
        pg_store.easyparcel_consume_state('state-a','cookie-a',now=103)
        assert False, 'state replay was accepted'
    except PermissionError: pass
    expired=pg_store.easyparcel_link_ticket(owner,'api',now=100)
    try:
        pg_store.easyparcel_begin_link(expired,'state-c','cookie-c',now=401)
        assert False, 'expired ticket was accepted'
    except PermissionError: pass
