"""Server-side Streamlit-to-Render bridge; never sends IdP tokens to widgets."""
import json
import secrets
from urllib import error, request

BASE_URL = 'https://kargokawan-oauth.onrender.com'


def call_pilot(identity_token, method, path, payload=None, version=None, request_key=None, transport=None):
    if not isinstance(identity_token,str) or not identity_token or len(identity_token)>8192:
        return {'status':'NOT_CONNECTED','reason':'Operator identity token is unavailable.'}
    if not path.startswith('/pilot/') or '//' in path or '..' in path or '?' in path:
        raise ValueError('Invalid pilot API path.')
    if method not in ('GET','POST','PUT'):
        raise ValueError('Unsupported pilot API operation.')
    headers={'Authorization':'Bearer '+identity_token,'Accept':'application/json'}
    body=None
    if method in ('POST','PUT'):
        if payload is None: raise ValueError('A request body is required.')
        body=json.dumps(payload,allow_nan=False).encode()
        headers['Content-Type']='application/json'
        if method=='POST': headers['Idempotency-Key']=request_key or secrets.token_urlsafe(24)
        else:
            if version is None: raise ValueError('A current version is required.')
            headers['If-Match']=str(version)
    req=request.Request(BASE_URL+path,body,headers,method=method)
    sender=transport or (lambda item: request.urlopen(item,timeout=20 if path=='/pilot/easyparcel/sandbox-quotation' else 10))
    try:
        with sender(req) as response:
            return {'status':'OK','data':json.load(response)}
    except error.HTTPError as exc:
        reasons={400:'Request rejected. Check connection details or wait before retrying.',
                 401:'Sign in again.',403:'This operator is not authorised.',404:'Record unavailable to this operator.',
                 409:'Data changed; reload before saving.',503:'Pilot identity, OAuth configuration or persistent storage is unavailable.'}
        return {'status':'NOT_CONNECTED' if exc.code==503 else 'ERROR','reason':reasons.get(exc.code,'Pilot request failed.'),'http_status':exc.code}
    except (error.URLError,TimeoutError,OSError,ValueError):
        return {'status':'ERROR','reason':'Pilot backend could not be reached or returned an invalid response.'}
