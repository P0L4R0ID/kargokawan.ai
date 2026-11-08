"""Server-only, owner-scoped draft job/quote API. No carrier write endpoints."""
import json
import os
import re
import sqlite3
import psycopg
from psycopg_pool import PoolTimeout
from psycopg.conninfo import conninfo_to_dict
from functools import lru_cache
from decimal import Decimal, InvalidOperation
from pathlib import Path
from pilot_store import OperatorVerifier, PilotStore
from postgres_pilot_store import PostgresPilotStore

MAX_BODY = 65536
RECORD_ID = r'[A-Za-z0-9-]{1,80}'
JOB_PATH = re.compile(r'^/pilot/jobs/(' + RECORD_ID + r')$')
QUOTES_PATH = re.compile(r'^/pilot/jobs/(' + RECORD_ID + r')/quotes$')
QUOTE_PATH = re.compile(r'^/pilot/jobs/(' + RECORD_ID + r')/quotes/(' + RECORD_ID + r')$')
ORDER_FIELDS = {'order_id','origin','destination','weight_kg','length_cm','width_cm','height_cm',
                'deadline_days','recipient','origin_postcode','destination_postcode'}
QUOTE_FIELDS = set('quote_id source_class provider service transport_method origin_postcode destination_postcode pickup_location dropoff_locations shipment_ids physical_weight_kg length_cm width_cm height_cm capacity_kg displayed_cost_myr full_cost tax_status surcharge_status source_reference collected_at valid_until transit_days restrictions'.split())


def configured_store(env=None, mount_check=None, persistent_root='/var/data'):
    """Return None until every production identity and storage prerequisite holds."""
    env = env if env is not None else os.environ
    mount_check = mount_check or os.path.ismount
    if env.get('PILOT_ENABLED') != '1':
        return None
    names = ('PILOT_OIDC_ISSUER','PILOT_OIDC_AUDIENCE','PILOT_OIDC_SUBJECT', 'PILOT_OIDC_JWKS_URL')
    if any(not env.get(name) for name in names):
        return None
    try:
        identity = tuple(env[name] for name in names)
        backend = env.get('PILOT_DB_BACKEND')
        if backend == 'postgres':
            url = env.get('PILOT_DATABASE_URL', '')
            parsed = conninfo_to_dict(url)
            if not all(parsed.get(name) for name in ('host', 'user', 'password', 'dbname')):
                return None
            if parsed.get('sslmode') not in (None, 'verify-full'):
                return None
            ca = env.get('PILOT_DATABASE_CA_FILE', '')
            if not ca or not Path(ca).is_file():
                return None
            return _cached_postgres(url, ca, *identity)
        if backend != 'sqlite' or not env.get('PILOT_DB') or not mount_check(persistent_root):
            return None
        path = Path(env['PILOT_DB']).resolve()
        if Path(persistent_root).resolve() not in path.parents:
            return None
        return _cached_store(str(path), str(Path(persistent_root).resolve()), *identity)
    except (ValueError, OSError, RuntimeError, sqlite3.Error, psycopg.Error, PoolTimeout):
        return None


@lru_cache(maxsize=4)
def _cached_store(path,root,issuer,audience,subject,jwks_url):
    verifier=OperatorVerifier(issuer,audience,subject,jwks_url=jwks_url)
    return PilotStore(path,verifier,root)


@lru_cache(maxsize=2)
def _cached_postgres(url, ca, issuer, audience, subject, jwks_url):
    verifier = OperatorVerifier(issuer, audience, subject, jwks_url=jwks_url)
    return PostgresPilotStore(url, verifier, conn_kwargs={
        'sslmode': 'verify-full', 'sslrootcert': ca, 'connect_timeout': 5,
        'application_name': 'kargokawan_pilot'})


def _response(start_response, status, value):
    data = json.dumps(value, separators=(',', ':'), allow_nan=False).encode()
    start_response(status, [('Content-Type','application/json'),('Content-Length',str(len(data))),
                            ('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),
                            ('Referrer-Policy','no-referrer')])
    return [data]


def _body(environ):
    if environ.get('CONTENT_TYPE','').split(';')[0] != 'application/json':
        raise ValueError('JSON content type is required.')
    try:
        length = int(environ.get('CONTENT_LENGTH',''))
    except ValueError:
        raise ValueError('Content length is required.') from None
    if length < 2 or length > MAX_BODY:
        raise ValueError('Request body is too large or empty.')
    data = environ['wsgi.input'].read(length)
    if len(data) != length:
        raise ValueError('Incomplete request body.')
    try:
        value = json.loads(data)
    except (UnicodeError,ValueError):
        raise ValueError('Invalid JSON body.') from None
    if not isinstance(value,dict):
        raise ValueError('JSON object required.')
    return value


def _mutation_key(environ):
    key = environ.get('HTTP_IDEMPOTENCY_KEY','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',key):
        raise ValueError('A unique Idempotency-Key is required.')
    return key


def _version(environ):
    value = environ.get('HTTP_IF_MATCH','')
    if not re.fullmatch(r'[1-9][0-9]{0,9}',value):
        raise ValueError('If-Match must contain the current numeric version.')
    return int(value)


def _orders(value):
    if not isinstance(value,list) or not 1<=len(value)<=20 or any(not isinstance(row,dict) or set(row)!=ORDER_FIELDS for row in value):
        raise ValueError('Provide 1–20 complete order records using the existing intake columns.')
    ids=[]
    for row in value:
        for field in ('order_id','origin','destination','recipient'):
            if not isinstance(row[field],str) or not row[field].strip() or len(row[field])>200:
                raise ValueError('Order identity, locations and recipient are required.')
        ids.append(row['order_id'])
        for field in ('origin_postcode','destination_postcode'):
            if not isinstance(row[field],str) or not re.fullmatch(r'\d{5}',row[field]):
                raise ValueError('Order postcodes must be five-digit strings.')
        for field in ('weight_kg','length_cm','width_cm','height_cm'):
            try: number=Decimal(str(row[field]))
            except (InvalidOperation,TypeError,ValueError): raise ValueError('Order dimensions and weight must be positive.') from None
            if not number.is_finite() or number<=0: raise ValueError('Order dimensions and weight must be positive.')
        deadline=str(row['deadline_days'])
        if isinstance(row['deadline_days'],bool) or not re.fullmatch(r'[1-9][0-9]{0,2}',deadline) or int(deadline)>365:
            raise ValueError('Order deadline must be 1–365 whole days.')
    if len(set(ids))!=len(ids): raise ValueError('Order IDs must be unique.')
    return value


def _quote(value):
    if not isinstance(value,dict) or not set(value)<=QUOTE_FIELDS:
        raise ValueError('Quote fields do not match the reviewed import schema.')
    if value.get('source_class') not in ('PUBLIC_REFERENCE','USER_IMPORTED_UNVERIFIED'):
        raise ValueError('Only manual or public-reference quote drafts may be saved.')
    if any(not isinstance(value.get(field),str) or not value[field].strip() for field in ('provider','service','source_reference')):
        raise ValueError('Provider, service and evidence reference are required.')
    return value


def handle(environ,start_response,store):
    route=environ.get('PATH_INFO','')
    method=environ.get('REQUEST_METHOD','GET')
    header=environ.get('HTTP_AUTHORIZATION','')
    if not header.startswith('Bearer ') or len(header)>8199:
        return _response(start_response,'401 Unauthorized',{'error':'Authenticated operator token required.'})
    if store is None:
        return _response(start_response,'503 Service Unavailable',{'status':'STORAGE_UNAVAILABLE',
            'reason':'Pilot identity or persistent storage is not configured.'})
    token=header[7:]
    try:
        store.verifier.verify(token)
    except PermissionError:
        return _response(start_response,'403 Forbidden',{'error':'Operator identity not authorized.'})
    try:
        if route=='/pilot/status' and method=='GET':
            if hasattr(store, 'health'):
                store.health()
            return _response(start_response,'200 OK',{'status':'READY','easyparcel_oauth':'NOT_CONNECTED'})
        if route=='/pilot/jobs':
            if method=='GET':
                return _response(start_response,'200 OK',{'job_ids':store.list_jobs(token)})
            if method=='POST':
                key=_mutation_key(environ);body=_body(environ)
                if set(body)!={'orders'}: raise ValueError('Only orders may be supplied.')
                job_id=store.create_job(token,_orders(body['orders']),idempotency_key=key)
                return _response(start_response,'201 Created',{'job_id':job_id,'version':store.job_snapshot(token,job_id)['version']})
        job=JOB_PATH.fullmatch(route)
        if job:
            job_id=job[1]
            if method=='GET':
                return _response(start_response,'200 OK',store.job_snapshot(token,job_id))
            if method=='PUT':
                version=_version(environ);body=_body(environ)
                if set(body)!={'orders'}: raise ValueError('Only orders may be supplied.')
                store.replace_job(token,job_id,_orders(body['orders']),expected_version=version)
                return _response(start_response,'200 OK',store.job_snapshot(token,job_id))
        quotes=QUOTES_PATH.fullmatch(route)
        if quotes:
            job_id=quotes[1]
            if method=='GET':
                return _response(start_response,'200 OK',{'quote_ids':store.list_quotes(token,job_id)})
            if method=='POST':
                key=_mutation_key(environ);body=_body(environ)
                if set(body)!={'quote'}: raise ValueError('Only quote may be supplied.')
                quote_id=store.create_quote(token,job_id,_quote(body['quote']),idempotency_key=key)
                return _response(start_response,'201 Created',{'quote_id':quote_id,'version':store.quote_snapshot(token,job_id,quote_id)['version']})
        quote=QUOTE_PATH.fullmatch(route)
        if quote:
            job_id,quote_id=quote[1],quote[2]
            if method=='GET':
                return _response(start_response,'200 OK',store.quote_snapshot(token,job_id,quote_id))
            if method=='PUT':
                version=_version(environ);body=_body(environ)
                if set(body)!={'quote'}: raise ValueError('Only quote may be supplied.')
                store.replace_quote(token,job_id,quote_id,_quote(body['quote']),expected_version=version)
                return _response(start_response,'200 OK',store.quote_snapshot(token,job_id,quote_id))
        return _response(start_response,'404 Not Found',{'error':'No pilot operation at this path.'})
    except PermissionError:
        return _response(start_response,'404 Not Found',{'error':'Record unavailable.'})
    except ValueError as exc:
        return _response(start_response,'409 Conflict' if 'changed' in str(exc) or 'reused' in str(exc) else '400 Bad Request',
                         {'error':str(exc)})
    except (sqlite3.Error, psycopg.Error, PoolTimeout):
        return _response(start_response,'503 Service Unavailable',{'status':'STORAGE_UNAVAILABLE',
            'reason':'Pilot storage is temporarily unavailable.'})
