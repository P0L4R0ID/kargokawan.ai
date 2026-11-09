"""Private planning integration; uses a disposable PostgreSQL database when configured."""
import io
import json
import time
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from hybrid_quotes import normalize
from oauth_callback import create_app
from tests.test_postgres_pilot_store import pg_store, identity


ORDERS = [
    {'order_id': oid, 'origin': 'Kuala Lumpur', 'destination': 'Fictional destination',
     'weight_kg': 1, 'length_cm': 10, 'width_cm': 10, 'height_cm': 10,
     'deadline_days': 3, 'recipient': 'Fictional recipient',
     'origin_postcode': '50000', 'destination_postcode': postcode}
    for oid, postcode in [('A', '10000'), ('B', '10001'), ('C', '10002')]
]


def quote(ids, cost, *, vehicle=False, source='USER_IMPORTED_UNVERIFIED', expiry_days=1):
    now = datetime.now(timezone.utc)
    postcodes = {row['order_id']: row['destination_postcode'] for row in ORDERS}
    stops = [{'shipment_id': oid, 'postcode': postcodes[oid], 'sequence': n + 1}
             for n, oid in enumerate(ids)]
    data = normalize({'quote_id': ('V' if vehicle else 'C') + ''.join(ids) + str(time.time_ns()),
        'source_class': source, 'provider': 'Lalamove Malaysia' if vehicle else 'EasyParcel Malaysia',
        'service': 'Test-only complete quote',
        'transport_method': 'multi_stop_vehicle' if vehicle else 'parcel_courier',
        'origin_postcode': '50000', 'destination_postcode': postcodes[ids[0]],
        'pickup_location': 'Fictional pickup',
        'dropoff_locations': json.dumps(stops) if vehicle else '',
        'shipment_ids': ';'.join(ids), 'physical_weight_kg': str(len(ids)),
        'length_cm': '20', 'width_cm': '20', 'height_cm': '20', 'capacity_kg': '10',
        'displayed_cost_myr': str(cost), 'full_cost': 'true', 'tax_status': 'included',
        'surcharge_status': 'included', 'source_reference': 'SYNTHETIC TEST FIXTURE — NO REAL QUOTE',
        'collected_at': (now - timedelta(days=2)).isoformat(),
        'valid_until': (now + timedelta(days=expiry_days)).isoformat(),
        'transit_days': '1', 'restrictions': 'none'})
    return json.loads(json.dumps(data, default=str))


def call(app, path, method='GET', token=None, body=None, key=None, version=None):
    raw = json.dumps(body).encode() if body is not None else b''
    env = {'PATH_INFO': path, 'REQUEST_METHOD': method, 'wsgi.input': io.BytesIO(raw),
           'CONTENT_LENGTH': str(len(raw)), 'CONTENT_TYPE': 'application/json'}
    if token: env['HTTP_AUTHORIZATION'] = 'Bearer ' + token
    if key: env['HTTP_IDEMPOTENCY_KEY'] = key
    if version is not None: env['HTTP_IF_MATCH'] = str(version)
    result = {}
    data = b''.join(app(env, lambda status, headers: result.update(status=status, headers=dict(headers))))
    try: payload = json.loads(data)
    except json.JSONDecodeError: payload = data.decode()
    return int(result['status'][:3]), payload


def setup_job(pg_store, identity):
    app = create_app(pilot_store=pg_store)
    token = identity[1]()
    status, created = call(app, '/pilot/jobs', 'POST', token, {'orders': ORDERS}, 'job-key-' + str(time.time_ns()))
    assert status == 201
    return app, token, created['job_id']


def add_quote(app, token, job, data):
    status, created = call(app, f'/pilot/jobs/{job}/quotes', 'POST', token,
                           {'quote': data}, 'quote-key-' + str(time.time_ns()))
    assert status == 201, created
    return created['quote_id']


def test_private_plan_not_ready_then_approval_and_manifest(pg_store, identity):
    app, token, job = setup_job(pg_store, identity)
    path = f'/pilot/jobs/{job}/proposals'
    status, empty = call(app, path, 'POST', token, {}, 'plan-key-' + str(time.time_ns()))
    assert status == 200 and empty['status'] == 'NOT READY'
    assert len(empty['missing_tasks']) == 3
    assert call(app, path, token=token)[1]['proposals'] == []
    for oid in 'ABC': add_quote(app, token, job, quote([oid], 20))
    add_quote(app, token, job, quote(['A', 'B'], 25, vehicle=True))
    key = 'plan-key-' + str(time.time_ns())
    status, proposal = call(app, path, 'POST', token, {}, key)
    assert status == 201 and proposal['status'] == 'READY'
    assert proposal['total_myr'] == '45' and proposal['baseline_myr'] == '60'
    assert proposal['provenance'].startswith('USER_IMPORTED_UNVERIFIED')
    assert {tuple(d['shipment_ids']) for d in proposal['decisions']} == {('A', 'B'), ('C',)}
    assert call(app, path, 'POST', token, {}, key)[1]['proposal_id'] == proposal['proposal_id']
    ppath = path + '/' + proposal['proposal_id']
    assert call(app, ppath + '/manifest', token=token)[0] == 400
    events = call(app, f'/pilot/jobs/{job}/audit', token=token)[1]['events']
    assert [event['action'] for event in events] == ['PLAN_PROPOSED']
    assert 'Fictional recipient' not in str(events)
    status, approved = call(app, ppath + '/approval', 'PUT', token, {}, version=1)
    assert status == 200 and approved['approval_status'] == 'APPROVED' and approved['version'] == 2
    assert call(app, ppath + '/approval', 'PUT', token, {}, version=1)[0] == 409
    status, manifest = call(app, ppath + '/manifest', token=token)
    assert status == 200 and manifest['filename'].endswith('.csv')
    assert manifest['csv'].count('NOT A BOOKING') == 3
    assert 'Fictional recipient' not in manifest['csv'] and 'Bearer ' not in manifest['csv']
    assert [event['action'] for event in call(app, f'/pilot/jobs/{job}/audit', token=token)[1]['events']] == [
        'PLAN_PROPOSED', 'PLAN_APPROVED']
    assert call(app, ppath, token=identity[1]('wrong'))[0] == 403
    assert call(app, ppath + '/manifest')[0] == 401


def test_stale_quote_availability_and_order_changes(pg_store, identity):
    app, token, job = setup_job(pg_store, identity)
    path = f'/pilot/jobs/{job}/proposals'
    quote_ids = [add_quote(app, token, job, quote([oid], 20)) for oid in 'ABC']
    status, proposal = call(app, path, 'POST', token, {}, 'plan-key-' + str(time.time_ns()))
    assert status == 201
    ppath = path + '/' + proposal['proposal_id']
    qpath = f'/pilot/jobs/{job}/quotes/{quote_ids[0]}'
    saved = call(app, qpath, token=token)[1]['quote']
    saved['displayed_cost_myr'] = '21'
    assert call(app, qpath, 'PUT', token, {'quote': saved}, version=1)[0] == 200
    assert call(app, ppath + '/approval', 'PUT', token, {}, version=1)[0] == 409
    assert all(e['action'] != 'PLAN_APPROVED' for e in call(app, f'/pilot/jobs/{job}/audit', token=token)[1]['events'])
    status, second = call(app, path, 'POST', token, {}, 'plan-key-' + str(time.time_ns()))
    assert status == 201
    assert call(app, f'/pilot/jobs/{job}/availability', 'PUT', token,
                {'unavailable': ['EasyParcel Malaysia']}, version=1)[0] == 200
    assert call(app, path + '/' + second['proposal_id'] + '/approval', 'PUT', token, {}, version=1)[0] == 409
    assert call(app, path, 'POST', token, {}, 'plan-key-' + str(time.time_ns()))[1]['status'] == 'NOT READY'
    changed = [dict(order) for order in ORDERS]
    changed[0]['weight_kg'] = 2
    assert call(app, f'/pilot/jobs/{job}', 'PUT', token, {'orders': changed}, version=2)[0] == 200
    assert call(app, path + '/' + second['proposal_id'] + '/approval', 'PUT', token, {}, version=1)[0] == 409


def test_excluded_public_expired_and_incomplete_quotes(pg_store, identity):
    app, token, job = setup_job(pg_store, identity)
    add_quote(app, token, job, quote(['A'], 20, source='PUBLIC_REFERENCE'))
    add_quote(app, token, job, quote(['B'], 20, expiry_days=-1))
    add_quote(app, token, job, {'source_class': 'USER_IMPORTED_UNVERIFIED', 'provider': 'EasyParcel Malaysia',
                               'service': 'Parcel', 'source_reference': 'INCOMPLETE TEST FIXTURE'})
    status, result = call(app, f'/pilot/jobs/{job}/proposals', 'POST', token, {},
                          'plan-key-' + str(time.time_ns()))
    assert status == 200 and result['status'] == 'NOT READY'
    assert len(result['missing_tasks']) == 3
    assert {x['status'] for x in result['reviewed']} >= {'EXCLUDED'}
    assert call(app, f'/pilot/jobs/{job}/audit', token=token)[1]['events'] == []


def test_database_owner_predicates_and_append_only_audit(pg_store, identity):
    app, token, job = setup_job(pg_store, identity)
    for oid in 'ABC': add_quote(app, token, job, quote([oid], 20))
    proposal = call(app, f'/pilot/jobs/{job}/proposals', 'POST', token, {},
                    'plan-key-' + str(time.time_ns()))[1]
    with pg_store.pool.connection() as db:
        with pytest.raises(psycopg.Error):
            db.execute('UPDATE pilot_audit SET action=%s WHERE job_id=%s', ('TAMPERED', job))
    with pg_store.pool.connection() as db:
        with db.transaction():
            db.execute('UPDATE pilot_jobs SET owner_sub=%s WHERE job_id=%s', ('someone-else', job))
    ppath = f'/pilot/jobs/{job}/proposals/{proposal["proposal_id"]}'
    assert call(app, ppath, token=token)[0] == 404
    assert call(app, ppath + '/approval', 'PUT', token, {}, version=1)[0] == 404
    assert call(app, ppath + '/manifest', token=token)[0] == 404
    assert call(app, f'/pilot/jobs/{job}/audit', token=token)[0] == 404


def test_pilot_planning_ui_with_injected_authenticated_backend():
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest
    import pilot_ui

    class FakeUser(dict):
        is_logged_in = True
        tokens = {'id': 'signed-test-id-token'}
    user = FakeUser(sub='allowed', exp=int(time.time()) + 300)
    auth = {'redirect_uri': 'https://pilot.example/oauth2callback', 'cookie_secret': 'test-only',
            'client_id': 'test-only', 'client_secret': 'test-only',
            'server_metadata_url': 'https://issuer.example/.well-known/openid-configuration',
            'expose_tokens': 'id'}
    def fake_call(token, method, path, payload=None, version=None, request_key=None):
        assert token == 'signed-test-id-token'
        if path == '/pilot/status': return {'status': 'OK', 'data': {'status': 'READY'}}
        if path == '/pilot/easyparcel/connection':
            return {'status':'OK','data':{'status':'CONNECTED','environment':'UNKNOWN','linked_at':1}}
        if path == '/pilot/easyparcel/sandbox-quotation' and method == 'POST':
            assert payload == {}
            return {'status':'OK','data':{'environment':'UNKNOWN','sample_input':'FICTIONAL PDF EXAMPLE',
                'observations':[{'courier_name':'FICTIONAL TEST COURIER','total_amount_myr':'12.31'}],
                'errors':[]}}
        if path == '/pilot/jobs': return {'status': 'OK', 'data': {'job_ids': ['PILOT-TEST']}}
        if path == '/pilot/jobs/PILOT-TEST': return {'status': 'OK', 'data': {'orders': ORDERS, 'version': 1}}
        if path.endswith('/quotes'): return {'status': 'OK', 'data': {'quote_ids': []}}
        if path.endswith('/availability'): return {'status': 'OK', 'data': {'unavailable': []}}
        if path.endswith('/easyparcel/readiness'):
            return {'status': 'OK', 'data': {'connector': {'status': 'NOT_CONNECTED', 'reason': 'Disabled.'},
                    'missing_quote_tasks': [{'order_id': 'A', 'action': 'Obtain a quote.'}],
                    'manual_quote_previews': []}}
        if path.endswith('/proposals') and method == 'GET': return {'status': 'OK', 'data': {'proposals': []}}
        if path.endswith('/proposals') and method == 'POST':
            return {'status': 'OK', 'data': {'status': 'NOT READY', 'reason': 'No complete quote cover.',
                    'missing_tasks': ['Collect a quote for A.'], 'reviewed': []}}
        if path.endswith('/audit'): return {'status': 'OK', 'data': {'events': []}}
        raise AssertionError((method, path))
    with patch('pilot_ui._secrets', return_value={'auth': auth, 'PILOT_OPERATOR_SUB': 'allowed'}), \
         patch('pilot_ui.st.user', user), patch('pilot_ui.call_pilot', side_effect=fake_call):
        app = AppTest.from_string('from pilot_ui import render\nrender()', default_timeout=20).run()
        assert not app.exception
        assert any(button.label == 'Prepare EasyParcel Connect' for button in app.button)
        next(button for button in app.button if button.label == 'Check one fictional EasyParcel sample rate').click().run()
        assert not app.exception
        assert any('FICTIONAL TEST COURIER' in str(frame.value) for frame in app.dataframe)
        assert any(button.label == 'Check EasyParcel rates' for button in app.button)
        assert any('Orders to quote' in widget.label for widget in app.multiselect)
        next(button for button in app.button if button.label == 'Request private plan').click().run()
        assert not app.exception
        assert any('NOT READY' in warning.value for warning in app.warning)
        assert any('Collect a quote for A.' in item.value for item in app.markdown)
        next(button for button in app.button if button.label == 'Preview synthetic EasyParcel fixture').click().run()
        assert not app.exception
        assert any('TEST_ONLY' in str(frame.value) for frame in app.dataframe)


def test_migrates_existing_private_job_schema(identity):
    import os
    import uuid
    from psycopg.conninfo import make_conninfo
    from postgres_pilot_store import PostgresPilotStore
    original = os.environ.get('KK_TEST_POSTGRES_DSN')
    if not original:
        pytest.skip('Disposable PostgreSQL not configured')
    dbname = 'kk_migration_' + uuid.uuid4().hex[:12]
    maintenance = make_conninfo(original, dbname='postgres')
    with psycopg.connect(maintenance, autocommit=True) as admin:
        admin.execute('CREATE DATABASE ' + dbname)
    target = make_conninfo(original, dbname=dbname)
    try:
        with psycopg.connect(target) as db:
            db.execute('CREATE SCHEMA kargokawan_pilot')
            db.execute('SET search_path TO kargokawan_pilot')
            db.execute('CREATE TABLE pilot_schema_versions (version INTEGER PRIMARY KEY)')
            db.execute('INSERT INTO pilot_schema_versions VALUES (1)')
            db.execute('CREATE TABLE pilot_jobs (job_id TEXT PRIMARY KEY, owner_sub TEXT NOT NULL, orders_json TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1)')
            db.execute('CREATE TABLE pilot_quotes (quote_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES pilot_jobs(job_id) ON DELETE CASCADE, owner_sub TEXT NOT NULL, quote_json TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1)')
            db.execute('CREATE TABLE pilot_requests (owner_sub TEXT NOT NULL, request_key TEXT NOT NULL, request_hash TEXT NOT NULL, response_id TEXT NOT NULL, PRIMARY KEY(owner_sub,request_key))')
            db.execute('INSERT INTO pilot_jobs (job_id,owner_sub,orders_json) VALUES (%s,%s,%s)',
                       ('PILOT-LEGACY', 'allowed', json.dumps(ORDERS)))
        store = PostgresPilotStore(target, identity[0], min_size=0, max_size=1)
        try:
            assert store.get_job(identity[1](), 'PILOT-LEGACY') == ORDERS
            assert store.availability(identity[1](), 'PILOT-LEGACY') == []
            with store.pool.connection() as db:
                assert db.execute('SELECT version FROM pilot_schema_versions').fetchone() == (2,)
        finally:
            store.pool.close()
    finally:
        with psycopg.connect(maintenance, autocommit=True) as admin:
            admin.execute('DROP DATABASE ' + dbname + ' WITH (FORCE)')
