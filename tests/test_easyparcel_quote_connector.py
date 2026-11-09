"""No provider network requests or real credentials are used in these tests."""
import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from easyparcel_quote_connector import (EasyParcelOpenApiQuoteAdapter,
    FixtureEasyParcelQuoteAdapter, interpret_test_fixture, missing_shipment_facts,
    synthetic_demo_transport, manual_quote_readiness)
from mixed_method import optimize
from tests.test_pilot_planning import ORDERS, call, setup_job, quote, add_quote
from tests.test_postgres_pilot_store import identity, pg_store
from hybrid_quotes import normalize


def test_production_connector_never_calls_provider_even_if_flag_is_set():
    from unittest.mock import patch
    with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')) as send:
        for flag in ({}, {'EASYPARCEL_QUOTE_CONNECTOR_ENABLED': '1'}):
            adapter = EasyParcelOpenApiQuoteAdapter(flag)
            result = adapter.request_rates(ORDERS)
            assert result['status'] == 'NOT_CONNECTED' and result['credential_status'] == 'UNAVAILABLE'
            assert result['observations'] == [] and result['rejections'] == []
            assert 'OAuth' in result['reason'] or 'disabled' in result['reason']
        send.assert_not_called()


def test_fixture_normalization_is_synthetic_incomplete_and_excluded():
    order = ORDERS[0]
    result = FixtureEasyParcelQuoteAdapter(synthetic_demo_transport).request_rates([order])
    assert result['status'] == 'TEST_ONLY' and len(result['observations']) == 1
    evidence = result['observations'][0]
    assert evidence['source_class'] == 'SYNTHETIC' and evidence['review_status'] == 'INCOMPLETE'
    assert evidence['origin_postcode'] == '50000' and evidence['destination_postcode'] == '10000'
    assert evidence['covered_order_ids'] == ['A'] and evidence['displayed_cost_myr'] == '17.25'
    assert evidence['tax_myr'] is None and evidence['valid_until'] is None
    assert evidence['transit_days'] is None and not evidence['full_cost']
    assert 'TEST_ONLY' in evidence['source_reference']
    assert optimize(ORDERS, [])['status'] == 'NOT READY'
    complete = quote(['A'], 20)
    complete['source_class'] = 'SYNTHETIC'
    raw = {key: ';'.join(value) if key == 'shipment_ids' else json.dumps(value) if key == 'dropoff_locations' else str(value).lower() if isinstance(value, bool) else value
           for key, value in complete.items()}
    normalized = normalize(raw)
    assert optimize(ORDERS, [normalized])['status'] == 'NOT READY'


def test_fixture_preserves_disclosed_components_without_inventing_validity():
    payload = {'test_fixture': True, 'services': [{
        'service_id': 'TEST', 'service_name': 'Synthetic service',
        'displayed_cost_myr': '20.00', 'currency': 'MYR',
        'source_class': 'LIVE_AUTHENTICATED', 'full_cost': True,
        'tax_myr': '0.00', 'surcharge_myr': '2.00',
        'total_payable_myr': '22.00', 'delivery_text': 'approximately two days'}]}
    row = interpret_test_fixture(payload, ORDERS[0])['observations'][0]
    assert row['tax_myr'] == '0.00' and row['surcharge_myr'] == '2.00'
    assert row['total_payable_myr'] == '22.00' and row['valid_until'] is None
    assert row['transit_days'] is None and row['transit_guaranteed'] is None
    assert not row['full_cost'] and row['source_class'] == 'SYNTHETIC'


def test_missing_data_no_services_and_transport_are_distinct():
    order = dict(ORDERS[0], origin_postcode='5000', weight_kg=0)
    assert 'origin_postcode (five-digit postcode required)' in missing_shipment_facts(order)
    assert interpret_test_fixture(synthetic_demo_transport(order), order)['status'] == 'MISSING_SHIPMENT_DATA'
    assert interpret_test_fixture({'test_fixture': True, 'services': []}, ORDERS[0])['status'] == 'NO_SERVICES'
    assert interpret_test_fixture({'test_fixture': True, 'transport_error': 'synthetic'}, ORDERS[0])['status'] == 'TRANSPORT_ERROR'
    assert interpret_test_fixture({'test_fixture': True, 'authentication_error': 'synthetic'}, ORDERS[0])['status'] == 'AUTHENTICATION_ERROR'
    assert interpret_test_fixture({'services': []}, ORDERS[0])['status'] == 'UNTRUSTED_RESPONSE'
    assert FixtureEasyParcelQuoteAdapter(lambda _: (_ for _ in ()).throw(TimeoutError())).request_rates([ORDERS[0]])['rejections']


def test_fixture_rejects_bad_services_and_untrusted_response():
    payload = {'test_fixture': True, 'services': [
        {'service_id': 'TEST', 'service_name': 'S', 'displayed_cost_myr': '-1', 'currency': 'MYR'},
        {'service_id': 'TEST', 'service_name': 'S', 'displayed_cost_myr': '10', 'currency': 'USD'},
        {'service_id': 'TEST', 'service_name': 'S', 'displayed_cost_myr': '10', 'currency': 'MYR', 'tax_myr': 'unknown'},
        {'service_id': 'TEST', 'service_name': 'S', 'displayed_cost_myr': '10', 'currency': 'MYR', 'valid_until': 'not-a-time'},
        {'service_id': 'TEST', 'service_name': 'S', 'displayed_cost_myr': '10', 'currency': 'MYR', 'transit_days': '2-3 days'}]}
    result = interpret_test_fixture(payload, ORDERS[0])
    assert result['status'] == 'INVALID_RESPONSE' and len(result['rejections']) == 5
    with pytest.raises(ValueError):
        interpret_test_fixture({'test_fixture': True, 'services': []}, ORDERS[0], transport_label='claimed-live-endpoint')


def test_manual_readiness_marks_duplicates_and_incomplete():
    now = datetime.now(timezone.utc)
    data = quote(['A'], 20)
    payload = json.dumps(data)
    rows = [('PQUOTE-1', payload, 1), ('PQUOTE-2', payload, 1)]
    result = manual_quote_readiness('PILOT-TEST', ORDERS, rows)
    assert len(result['manual_quote_previews']) == 2
    assert result['manual_quote_previews'][0]['status'] == 'ELIGIBLE'
    assert result['manual_quote_previews'][1]['status'] == 'INELIGIBLE'
    assert [task['order_id'] for task in result['missing_quote_tasks']] == ['B', 'C']
    assert manual_quote_readiness('PILOT-TEST', ORDERS, rows, ['EasyParcel Malaysia'])['missing_quote_tasks']


def test_owner_scoped_readiness_and_stale_plan_after_quote_update(pg_store, identity):
    app, token, job = setup_job(pg_store, identity)
    path = f'/pilot/jobs/{job}/easyparcel/readiness'
    assert call(app, path)[0] == 401
    assert call(app, path, token=identity[1]('wrong'))[0] == 403
    status, result = call(app, path, token=token)
    assert status == 200 and result['connector']['status'] == 'NOT_CONNECTED'
    assert len(result['missing_quote_tasks']) == 3
    qids = [add_quote(app, token, job, quote([oid], 20)) for oid in 'ABC']
    status, result = call(app, path, token=token)
    assert status == 200 and result['missing_quote_tasks'] == []
    proposals = f'/pilot/jobs/{job}/proposals'
    proposal = call(app, proposals, 'POST', token, {}, 'plan-key-' + str(time.time_ns()))[1]
    saved_path = f'/pilot/jobs/{job}/quotes/{qids[0]}'
    saved = call(app, saved_path, token=token)[1]['quote']
    saved['displayed_cost_myr'] = '21.00'
    assert call(app, saved_path, 'PUT', token, {'quote': saved}, version=1)[0] == 200
    approval_path = proposals + '/' + proposal['proposal_id'] + '/approval'
    assert call(app, approval_path, 'PUT', token, {}, version=1)[0] == 409
    assert call(app, path, token=token)[1]['connector']['status'] == 'NOT_CONNECTED'
    with pg_store.pool.connection() as db:
        with db.transaction():
            db.execute('UPDATE pilot_jobs SET owner_sub=%s WHERE job_id=%s', ('other-owner', job))
    assert call(app, path, token=token)[0] == 404
