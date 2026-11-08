import io
from urllib.parse import urlsplit, parse_qs
from cryptography.fernet import Fernet
import pytest
from oauth_callback import create_app, configuration, get_stored_token, refresh_token

class FakeResponse:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, *args): return b'{"token_type":"Bearer","access_token":"private-token","refresh_token":"private-refresh"}'

def setup(tmp_path):
    return {'EASYPARCEL_OAUTH_CLIENT_ID':'test-client',
            'EASYPARCEL_OAUTH_CLIENT_SECRET':'test-secret',
            'EASYPARCEL_OAUTH_REDIRECT_URI':'https://backend.example/oauth/easyparcel/callback',
            'EASYPARCEL_OAUTH_DB':str(tmp_path/'tokens.sqlite'),
            'EASYPARCEL_OAUTH_FERNET_KEY':Fernet.generate_key().decode()}

def call(app,path,query='',cookie=''):
    captured={}
    def start(status,headers): captured.update(status=status,headers=dict(headers))
    body=b''.join(app({'PATH_INFO':path,'REQUEST_METHOD':'GET','QUERY_STRING':query,'HTTP_COOKIE':cookie},start)).decode()
    return captured['status'],captured['headers'],body

def test_callback_state_exchange_and_replay(tmp_path):
    env=setup(tmp_path)
    def transport(req):
        assert req.full_url=='https://api.easyparcel.com/oauth/token'
        assert req.get_header('Authorization').startswith('Basic ')
        assert b'grant_type=authorization_code' in req.data
        return FakeResponse()
    app=create_app(env,transport)
    status,headers,body=call(app,'/oauth/easyparcel/start')
    assert status=='302 Found' and headers['Location'].startswith('https://api.easyparcel.com/oauth/login?')
    assert 'Secure' in headers['Set-Cookie'] and 'HttpOnly' in headers['Set-Cookie']
    state=parse_qs(urlsplit(headers['Location']).query)['state'][0]
    cookie=headers['Set-Cookie'].split(';')[0]
    assert call(app,'/oauth/easyparcel/callback',f'code=abc&state={state}','wrong=cookie')[0]=='400 Bad Request'
    assert call(app,'/oauth/easyparcel/callback',f'code=abc&state={state}',cookie)[0]=='200 OK'
    assert call(app,'/oauth/easyparcel/callback',f'code=abc&state={state}',cookie)[0]=='400 Bad Request'
    assert 'private-token' not in (tmp_path/'tokens.sqlite').read_bytes().decode('latin1')
    session=cookie.split('=',1)[1]
    assert get_stored_token(env['EASYPARCEL_OAUTH_DB'],env['EASYPARCEL_OAUTH_FERNET_KEY'],session)['access_token']=='private-token'

def test_bad_redirect_and_expired_state(tmp_path):
    env=setup(tmp_path)
    env['EASYPARCEL_OAUTH_REDIRECT_URI']='http://backend.example/oauth/easyparcel/callback'
    with pytest.raises(ValueError): configuration(env)
    env['EASYPARCEL_OAUTH_REDIRECT_URI']='https://backend.example/oauth/easyparcel/callback'
    clock=[100]
    app=create_app(env,lambda req: FakeResponse(),lambda:clock[0])
    _,headers,_=call(app,'/oauth/easyparcel/start')
    state=parse_qs(urlsplit(headers['Location']).query)['state'][0]
    clock[0]=701
    assert call(app,'/oauth/easyparcel/callback',f'code=abc&state={state}',headers['Set-Cookie'].split(';')[0])[0]=='400 Bad Request'

def test_refresh_uses_documented_grant(tmp_path):
    env=configuration(setup(tmp_path))
    def transport(req):
        assert b'grant_type=refresh_token' in req.data
        assert b'private-refresh' in req.data
        return FakeResponse()
    assert refresh_token(env,'private-refresh',transport)['token_type']=='Bearer'
