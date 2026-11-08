"""Use KK_TEST_POSTGRES_DSN for disposable PostgreSQL integration coverage."""
import base64
import os
import time
from unittest.mock import patch

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from pilot_api import configured_store
from pilot_store import OperatorVerifier
from postgres_pilot_store import PostgresPilotStore


@pytest.fixture
def identity():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private.public_key().public_numbers()
    encode = lambda n: base64.urlsafe_b64encode(n.to_bytes((n.bit_length()+7)//8, 'big')).rstrip(b'=').decode()
    verifier = OperatorVerifier('https://issuer.example', 'client', 'allowed',
                                jwks={'keys': [{'kid': 'one', 'kty': 'RSA', 'n': encode(numbers.n), 'e': encode(numbers.e)}]})
    def token(subject='allowed', **changes):
        claims = {'iss': 'https://issuer.example', 'aud': 'client', 'sub': subject,
                  'iat': int(time.time()), 'exp': int(time.time()) + 300}
        claims.update(changes)
        return jwt.encode(claims, private, algorithm='RS256', headers={'kid': 'one'})
    return verifier, token


@pytest.fixture
def pg_store(identity):
    dsn = os.environ.get('KK_TEST_POSTGRES_DSN')
    if not dsn:
        pytest.skip('Disposable PostgreSQL not configured')
    with psycopg.connect(dsn) as setup_db:
        setup_db.execute('CREATE SCHEMA IF NOT EXISTS kargokawan_pilot')
    store = PostgresPilotStore(dsn, identity[0], min_size=0, max_size=2)
    yield store
    store.pool.close()


def test_postgres_owner_scope_versions_idempotency_and_order_invalidation(pg_store, identity):
    token = identity[1]()
    wrong = identity[1]('other')
    orders = [{'order_id': 'FICTIONAL-1', 'origin_postcode': '05000'}]
    key = 'test-' + str(time.time_ns())
    job = pg_store.create_job(token, orders, key)
    assert pg_store.create_job(token, orders, key) == job
    with pytest.raises(ValueError, match='reused'):
        pg_store.create_job(token, [{'order_id': 'different'}], key)
    assert job in pg_store.list_jobs(token)
    assert pg_store.job_snapshot(token, job) == {'orders': orders, 'version': 1}
    with pytest.raises(PermissionError):
        pg_store.get_job(wrong, job)
    with pytest.raises(PermissionError):
        pg_store.get_job(token, 'PILOT-UNKNOWN')
    quote = {'source_class': 'USER_IMPORTED_UNVERIFIED', 'provider': 'Fictional'}
    quote_key = key + '-quote'
    qid = pg_store.create_quote(token, job, quote, quote_key)
    assert pg_store.create_quote(token, job, quote, quote_key) == qid
    assert pg_store.quote_snapshot(token, job, qid)['version'] == 1
    with pytest.raises(ValueError):
        pg_store.create_quote(token, job, {'source_class': 'LIVE_AUTHENTICATED'}, key + '-forbidden')
    with pytest.raises(PermissionError):
        pg_store.get_quote(wrong, job, qid)
    pg_store.replace_quote(token, job, qid, dict(quote, service='Parcel'), expected_version=1)
    with pytest.raises(ValueError, match='changed'):
        pg_store.replace_quote(token, job, qid, quote, expected_version=1)
    with pytest.raises(ValueError, match='changed'):
        pg_store.replace_job(token, job, orders, expected_version=99)
    assert pg_store.list_quotes(token, job) == [qid]
    pg_store.replace_job(token, job, [{'order_id': 'FICTIONAL-2'}], expected_version=1)
    assert pg_store.list_quotes(token, job) == []
    with pytest.raises(PermissionError):
        pg_store.get_quote(token, job, qid)
    new_qid = pg_store.create_quote(token, job, quote, quote_key)
    assert new_qid != qid
    pg_store.delete_quote(token, job, new_qid)
    assert pg_store.list_quotes(token, job) == []


def test_postgres_independent_process_store_persists(pg_store, identity):
    token = identity[1]()
    job = pg_store.create_job(token, [{'order_id': 'FICTIONAL-PERSIST'}])
    second = PostgresPilotStore(os.environ['KK_TEST_POSTGRES_DSN'], identity[0], min_size=0, max_size=1)
    try:
        assert second.get_job(token, job)[0]['order_id'] == 'FICTIONAL-PERSIST'
    finally:
        second.pool.close()


def test_postgres_rejects_expired_and_invalid_identity(pg_store, identity):
    expired = identity[1](exp=int(time.time()) - 120)
    wrong_audience = identity[1](aud='wrong')
    for bad in (expired, wrong_audience, 'not-a-token'):
        with pytest.raises(PermissionError):
            pg_store.list_jobs(bad)


def test_postgres_failed_correction_rolls_back_quotes(pg_store, identity):
    token = identity[1]()
    job = pg_store.create_job(token, [{'order_id': 'FICTIONAL-ROLLBACK'}])
    quote = pg_store.create_quote(token, job, {'source_class': 'PUBLIC_REFERENCE'})
    with pytest.raises(ValueError, match='changed'):
        pg_store.replace_job(token, job, [{'order_id': 'CHANGED'}], expected_version=99)
    assert pg_store.job_snapshot(token, job)['version'] == 1
    assert pg_store.list_quotes(token, job) == [quote]
    with pytest.raises(ValueError):
        pg_store.replace_job(token, job, [{'bad': float('nan')}], expected_version=1)
    assert pg_store.job_snapshot(token, job)['version'] == 1
    assert pg_store.list_quotes(token, job) == [quote]


def test_postgres_rejects_unknown_schema_version(pg_store, identity):
    dsn = os.environ['KK_TEST_POSTGRES_DSN']
    with psycopg.connect(dsn, options='-c search_path=kargokawan_pilot') as db:
        db.execute('INSERT INTO pilot_schema_versions (version) VALUES (99)')
    try:
        with pytest.raises(RuntimeError, match='schema version'):
            PostgresPilotStore(dsn, identity[0], min_size=0, max_size=1)
    finally:
        with psycopg.connect(dsn, options='-c search_path=kargokawan_pilot') as db:
            db.execute('DELETE FROM pilot_schema_versions WHERE version=99')


def test_explicit_backend_never_falls_back_to_sqlite(tmp_path):
    env = {'PILOT_ENABLED': '1', 'PILOT_OIDC_ISSUER': 'https://issuer.example',
           'PILOT_OIDC_AUDIENCE': 'client', 'PILOT_OIDC_SUBJECT': 'allowed',
           'PILOT_OIDC_JWKS_URL': 'https://issuer.example/jwks',
           'PILOT_DB': str(tmp_path / 'pilot.sqlite')}
    assert configured_store(env, mount_check=lambda _: True, persistent_root=tmp_path) is None
    env['PILOT_DB_BACKEND'] = 'postgres'
    assert configured_store(env, mount_check=lambda _: True, persistent_root=tmp_path) is None
    env['PILOT_DATABASE_URL'] = 'postgresql://user:password@database.example/postgres?sslmode=disable'
    env['PILOT_DATABASE_CA_FILE'] = str(tmp_path / 'ca.pem')
    (tmp_path / 'ca.pem').write_text('test certificate placeholder')
    assert configured_store(env) is None
    env['PILOT_DATABASE_URL'] = 'postgresql://user:password@database.example/postgres'
    with patch('pilot_api._cached_postgres') as build:
        sentinel = object()
        build.return_value = sentinel
        assert configured_store(env) is sentinel
        assert build.call_args.args[1] == str(tmp_path / 'ca.pem')
        build.side_effect = psycopg.OperationalError('synthetic unavailable')
        assert configured_store(env) is None
    env['PILOT_DB_BACKEND'] = 'unknown'
    assert configured_store(env, mount_check=lambda _: True, persistent_root=tmp_path) is None


def test_concurrent_retry_creates_one_job(pg_store, identity):
    from concurrent.futures import ThreadPoolExecutor
    token = identity[1]()
    key = 'parallel-' + str(time.time_ns())
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: pg_store.create_job(token, [{'order_id': 'FICTIONAL'}], key), range(2)))
    assert results[0] == results[1]


def test_postgres_api_requires_identity_and_never_books(pg_store, identity):
    import io
    import json
    from oauth_callback import create_app
    app = create_app(pilot_store=pg_store)
    def call(path, token=None):
        env = {'PATH_INFO': path, 'REQUEST_METHOD': 'GET', 'wsgi.input': io.BytesIO(),
               'CONTENT_LENGTH': '0'}
        if token:
            env['HTTP_AUTHORIZATION'] = 'Bearer ' + token
        result = {}
        body = b''.join(app(env, lambda status, headers: result.update(status=status, headers=dict(headers))))
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError:
            decoded = body.decode()
        return result['status'], decoded
    assert call('/pilot/status')[0].startswith('401')
    assert call('/pilot/status', identity[1]('wrong'))[0].startswith('403')
    status, body = call('/pilot/status', identity[1]())
    assert status.startswith('200') and body == {'status': 'READY', 'easyparcel_oauth': 'NOT_CONNECTED'}
    assert call('/oauth/easyparcel/start', identity[1]())[0].startswith('403')
    assert call('/pilot/book', identity[1]())[0].startswith('404')
    pg_store.pool.close()
    status, body = call('/pilot/status', identity[1]())
    assert status.startswith('503') and body['status'] == 'STORAGE_UNAVAILABLE'
