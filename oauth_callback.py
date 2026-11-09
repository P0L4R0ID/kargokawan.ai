"""Separate WSGI callback for EasyParcel Open API authorization-code OAuth.

The legacy isolated SQLite flow is test-only. Production requires explicit
enablement, signed pilot identity and encrypted owner-scoped PostgreSQL tokens.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from http.cookies import SimpleCookie
from urllib import parse, request, error
from cryptography.fernet import Fernet

AUTHORIZE_URL = 'https://api.easyparcel.com/oauth/login'
TOKEN_URL = 'https://api.easyparcel.com/oauth/token'
COOKIE = 'kk_easyparcel_oauth_session'
FRONTEND_ORIGIN = 'https://kargokawan.streamlit.app'
BACKEND_ORIGIN = 'https://kargokawan-oauth.onrender.com'


def configuration(env=None):
    env = env if env is not None else os.environ
    names = ('EASYPARCEL_OAUTH_PLATFORM_URL', 'EASYPARCEL_OAUTH_CLIENT_ID', 'EASYPARCEL_OAUTH_CLIENT_SECRET',
             'EASYPARCEL_OAUTH_REDIRECT_URI', 'EASYPARCEL_OAUTH_DB', 'EASYPARCEL_OAUTH_FERNET_KEY')
    missing = [name for name in names if not env.get(name)]
    if missing:
        raise ValueError('Missing OAuth server configuration: ' + ', '.join(missing))
    redirect = env['EASYPARCEL_OAUTH_REDIRECT_URI']
    parsed = parse.urlsplit(redirect)
    if env['EASYPARCEL_OAUTH_PLATFORM_URL'].rstrip('/') != FRONTEND_ORIGIN:
        raise ValueError('Platform URL does not match the verified frontend origin.')
    if (redirect != BACKEND_ORIGIN + '/oauth/easyparcel/callback'
            or parsed.scheme != 'https' or not parsed.hostname or parsed.port is not None
            or parsed.username or parsed.password or parsed.hostname in ('localhost', '127.0.0.1')
            or parsed.hostname == parse.urlsplit(FRONTEND_ORIGIN).hostname
            or parsed.path != '/oauth/easyparcel/callback' or parsed.query or parsed.fragment):
        raise ValueError('Redirect URI must be the exact public HTTPS callback URL.')
    Fernet(env['EASYPARCEL_OAUTH_FERNET_KEY'].encode())
    return {name: env[name] for name in names}


def _db(path):
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS pending (state_hash TEXT PRIMARY KEY, session_hash TEXT NOT NULL, expires_at INTEGER NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS tokens (session_hash TEXT PRIMARY KEY, ciphertext BLOB NOT NULL, updated_at INTEGER NOT NULL)')
    return db


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _response(start_response, status, body, headers=()):
    data = body.encode()
    start_response(status, [('Content-Type', 'text/plain; charset=utf-8'),
                            ('Content-Length', str(len(data))), ('Cache-Control', 'no-store'),
                            ('Referrer-Policy', 'no-referrer'), *headers])
    return [data]


def _exchange(config, code, transport=None):
    basic = base64.b64encode((config['EASYPARCEL_OAUTH_CLIENT_ID'] + ':' + config['EASYPARCEL_OAUTH_CLIENT_SECRET']).encode()).decode()
    form = {'grant_type': 'authorization_code', 'redirect_uri': config['EASYPARCEL_OAUTH_REDIRECT_URI'], 'code': code}
    req = request.Request(TOKEN_URL, parse.urlencode(form).encode(),
                          {'Authorization': 'Basic ' + basic, 'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
    sender = transport or (lambda item: request.urlopen(item, timeout=10))
    with sender(req) as response:
        result = json.load(response)
    if not isinstance(result, dict) or result.get('token_type', '').lower() != 'bearer' or not result.get('access_token'):
        raise ValueError('Invalid provider token response.')
    return result


def refresh_token(config, refresh, transport=None):
    """Server-only refresh using the documented token endpoint and Basic client auth."""
    basic = base64.b64encode((config['EASYPARCEL_OAUTH_CLIENT_ID'] + ':' + config['EASYPARCEL_OAUTH_CLIENT_SECRET']).encode()).decode()
    form = {'grant_type': 'refresh_token', 'redirect_uri': config['EASYPARCEL_OAUTH_REDIRECT_URI'],
            'refresh_token': refresh}
    req = request.Request(TOKEN_URL, parse.urlencode(form).encode(),
                          {'Authorization': 'Basic ' + basic, 'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
    sender = transport or (lambda item: request.urlopen(item, timeout=10))
    with sender(req) as response:
        result = json.load(response)
    if not isinstance(result, dict) or result.get('token_type', '').lower() != 'bearer' or not result.get('access_token'):
        raise ValueError('Invalid provider token response.')
    return result


def create_app(env=None, token_transport=None, clock=None, enable_test_flow=False, pilot_store=None,
               easyparcel_service=None):
    """Build disabled-by-default OAuth and authenticated pilot endpoints."""
    if enable_test_flow and (env is None or token_transport is None):
        raise ValueError('The test flow requires explicit configuration and a mock transport.')
    config = configuration(env) if enable_test_flow else None
    clock = clock or time.time
    crypt = Fernet(config['EASYPARCEL_OAUTH_FERNET_KEY'].encode()) if config else None
    path = config['EASYPARCEL_OAUTH_DB'] if config else None
    from pilot_easyparcel import configuration as pilot_oauth_configuration
    pilot_config = pilot_oauth_configuration(env)

    def active_store():
        if pilot_store is not None:
            return pilot_store
        from pilot_api import configured_store
        return configured_store(env)

    def production_oauth(environ, start_response, store):
        from postgres_pilot_store import PostgresPilotStore
        from pilot_easyparcel import AUTH_HOSTS, save_authorization
        if pilot_config is None or not isinstance(store, PostgresPilotStore):
            return _response(start_response, '403 Forbidden', 'EasyParcel account linking is not available.')
        if environ.get('HTTP_HOST') != parse.urlsplit(pilot_config['EASYPARCEL_OAUTH_REDIRECT_URI']).netloc:
            return _response(start_response, '400 Bad Request', 'Callback origin is invalid.')
        if environ.get('REQUEST_METHOD') != 'GET':
            return _response(start_response, '405 Method Not Allowed', 'Method not allowed.')
        route = environ.get('PATH_INFO')
        params = parse.parse_qs(environ.get('QUERY_STRING',''), keep_blank_values=True)
        if route == '/oauth/easyparcel/start':
            if len(params.get('ticket',[])) != 1 or not params['ticket'][0]:
                return _response(start_response, '400 Bad Request', 'Link request is missing.')
            session, state = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            try:
                host = store.easyparcel_begin_link(params['ticket'][0], state, session, int(clock()))
            except PermissionError:
                return _response(start_response, '400 Bad Request', 'Link request expired or was already used.')
            url = AUTH_HOSTS[host] + '?' + parse.urlencode({
                'client_id':pilot_config['EASYPARCEL_OAUTH_CLIENT_ID'],
                'redirect_uri':pilot_config['EASYPARCEL_OAUTH_REDIRECT_URI'], 'state':state})
            cookie = f'{COOKIE}={session}; Path=/oauth/easyparcel; Max-Age=600; Secure; HttpOnly; SameSite=Lax'
            return _response(start_response, '302 Found', '', [('Location',url),('Set-Cookie',cookie)])
        cookies = SimpleCookie()
        try:
            cookies.load(environ.get('HTTP_COOKIE',''))
            session = cookies[COOKIE].value if COOKIE in cookies else ''
        except Exception:
            session = ''
        if len(params.get('state',[])) != 1 or not params['state'][0] or not session:
            return _response(start_response, '400 Bad Request', 'Authorization state was not verified.')
        try:
            owner = store.easyparcel_consume_state(params['state'][0], session, int(clock()))
        except PermissionError:
            return _response(start_response, '400 Bad Request', 'Authorization state was not verified.')
        cleared = f'{COOKIE}=; Path=/oauth/easyparcel; Max-Age=0; Secure; HttpOnly; SameSite=Lax'
        if 'error' in params or len(params.get('code',[])) != 1 or not params['code'][0]:
            return _response(start_response, '400 Bad Request', 'Provider authorization was not completed.', [('Set-Cookie',cleared)])
        try:
            token = _exchange(pilot_config, params['code'][0], token_transport)
            save_authorization(store, owner, pilot_config, token, int(clock()))
        except (ValueError, error.HTTPError, error.URLError, TimeoutError, OSError):
            return _response(start_response, '502 Bad Gateway', 'Provider token exchange failed.', [('Set-Cookie',cleared)])
        return _response(start_response, '200 OK',
            'EasyParcel account linked. Account environment is unverified; return to the private pilot.',
            [('Set-Cookie',cleared)])

    def app(environ, start_response):
        route = environ.get('PATH_INFO', '')
        if route == '/health':
            return _response(start_response, '200 OK', 'ok')
        if route.startswith('/pilot/'):
            from pilot_api import handle
            store=active_store()
            service=easyparcel_service
            if service is None and pilot_config is not None:
                from postgres_pilot_store import PostgresPilotStore
                if isinstance(store, PostgresPilotStore):
                    from pilot_easyparcel import PilotEasyParcelService
                    service=PilotEasyParcelService(store,pilot_config,token_transport=token_transport,clock=clock)
            return handle(environ,start_response,store,easyparcel_service=service,
                          oauth_config=pilot_config)
        if route in ('/oauth/easyparcel/start', '/oauth/easyparcel/callback') and not enable_test_flow:
            return production_oauth(environ,start_response,active_store())
        if route in ('/oauth/easyparcel/start', '/oauth/easyparcel/callback'):
            expected_host = parse.urlsplit(config['EASYPARCEL_OAUTH_REDIRECT_URI']).netloc
            if environ.get('HTTP_HOST') != expected_host:
                return _response(start_response, '400 Bad Request', 'Callback origin is invalid.')
        if environ.get('REQUEST_METHOD') != 'GET':
            return _response(start_response, '405 Method Not Allowed', 'Method not allowed.')
        if route == '/oauth/easyparcel/start':
            session = secrets.token_urlsafe(32)
            state = secrets.token_urlsafe(32)
            with _db(path) as db:
                db.execute('DELETE FROM pending WHERE expires_at < ?', (int(clock()),))
                db.execute('INSERT INTO pending VALUES (?, ?, ?)', (_hash(state), _hash(session), int(clock()) + 600))
            url = AUTHORIZE_URL + '?' + parse.urlencode({'client_id': config['EASYPARCEL_OAUTH_CLIENT_ID'],
                'redirect_uri': config['EASYPARCEL_OAUTH_REDIRECT_URI'], 'state': state})
            cookie = f'{COOKIE}={session}; Path=/oauth/easyparcel; Max-Age=600; Secure; HttpOnly; SameSite=Lax'
            return _response(start_response, '302 Found', '', [('Location', url), ('Set-Cookie', cookie)])
        if route != '/oauth/easyparcel/callback':
            return _response(start_response, '404 Not Found', 'Not found.')
        params = parse.parse_qs(environ.get('QUERY_STRING', ''), keep_blank_values=True)
        cookies = SimpleCookie()
        try:
            cookies.load(environ.get('HTTP_COOKIE', ''))
            session = cookies[COOKIE].value if COOKIE in cookies else ''
        except Exception:
            session = ''
        if len(params.get('state', [])) != 1 or not session:
            return _response(start_response, '400 Bad Request', 'Authorization state was not verified.')
        state = params['state'][0]
        with _db(path) as db:
            row = db.execute('SELECT session_hash, expires_at FROM pending WHERE state_hash=?', (_hash(state),)).fetchone()
            if not row or not hmac.compare_digest(row[0], _hash(session)) or row[1] < int(clock()):
                return _response(start_response, '400 Bad Request', 'Authorization state was not verified.')
            db.execute('DELETE FROM pending WHERE state_hash=?', (_hash(state),))
        if 'error' in params or len(params.get('code', [])) != 1 or not params['code'][0]:
            return _response(start_response, '400 Bad Request', 'Provider authorization was not completed.')
        try:
            token = _exchange(config, params['code'][0], token_transport)
            encrypted = crypt.encrypt(json.dumps(token).encode())
            with _db(path) as db:
                db.execute('INSERT OR REPLACE INTO tokens VALUES (?, ?, ?)', (_hash(session), encrypted, int(clock())))
        except (ValueError, error.HTTPError, error.URLError, TimeoutError, OSError):
            return _response(start_response, '502 Bad Gateway', 'Provider token exchange failed.')
        return _response(start_response, '200 OK', 'Provider authorization completed in the isolated test flow.')

    return app


def get_stored_token(db_path, fernet_key, session):
    """Server-only lookup; never call from Streamlit or return this to a browser."""
    with _db(db_path) as db:
        row = db.execute('SELECT ciphertext FROM tokens WHERE session_hash=?', (_hash(session),)).fetchone()
    return json.loads(Fernet(fernet_key.encode()).decrypt(row[0])) if row else None


def application(environ, start_response):
    """Gunicorn entry point; linking requires explicit secure configuration."""
    return create_app()(environ, start_response)
