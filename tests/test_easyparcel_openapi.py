"""Contract tests use fictional responses and never contact a carrier."""
import io
import json
from urllib.error import HTTPError

import pytest

from easyparcel_openapi import (STANDARD_URL, ONDEMAND_DOCUMENTED_URL, ProviderRateLimited,
                                standard_payload, parse_standard, request_standard,
                                validate_ondemand_waypoints, OwnerScopedReadOnlyQuoteService)


ORDER = {'order_id': 'FICTION-1', 'origin_postcode': '01000',
         'destination_postcode': '11950', 'weight_kg': '1.5',
         'width_cm': 5, 'length_cm': 6, 'height_cm': 7}
CODES = {'FICTION-1': {'sender': 'MY-02', 'receiver': 'MY-07'}}


def response(pricing=None, duration=None):
    return {'status_code': 200, 'request_id': 'synthetic-request', 'data': [
        {'status': 'success', 'input': standard_payload([ORDER], CODES)['shipment'][0],
         'quotations': [{'courier': {
            'service_id': 'EP-TEST', 'service_name': 'Synthetic service',
            'courier_id': 'TEST', 'courier_name': 'Fictional courier',
            'delivery_duration': duration}, 'pricing': pricing or {
                'currency': 'MYR', 'total_amount': '12.31',
                'seller_payable_amount': '2.11', 'shipment_price': '10.20',
                'shipment_tax': '0.61', 'coupon_discount': '1.00'}}]}]}


def test_payload_requires_exact_fields_and_preserves_zero_postcode():
    assert standard_payload([ORDER], CODES)['shipment'][0] == {
        'sender': {'postcode': '01000', 'subdivision_code': 'MY-02', 'country': 'MY'},
        'receiver': {'postcode': '11950', 'subdivision_code': 'MY-07', 'country': 'MY'},
        'weight': 1.5, 'width': 5.0, 'length': 6.0, 'height': 7.0}
    with pytest.raises(ValueError, match='subdivision'):
        standard_payload([ORDER], {})
    with pytest.raises(ValueError, match='postcodes|postcode'):
        standard_payload([{**ORDER, 'origin_postcode': '1000'}], CODES)
    with pytest.raises(ValueError, match='one to five'):
        standard_payload([ORDER] * 6, CODES)


def test_byoc_coupon_and_unknown_transit_are_review_only():
    item = parse_standard(response(), ['FICTION-1'], environment='Sandbox')['observations'][0]
    assert item['total_amount_myr'] == '12.31'
    assert item['seller_payable_amount_myr'] == '2.11'
    assert item['is_byoc_or_split_payable']
    assert item['pricing']['coupon_discount'] == '1.00'
    assert item['delivery_duration'] is None
    assert item['source_class'] == 'LIVE_AUTHENTICATED'
    assert item['review_status'] == 'NEEDS_REVIEW' and item['planner_eligible'] is False
    assert item['valid_until'] is None


def test_partial_errors_and_missing_pricing_never_enter_planner():
    result = response()
    result['data'].append({'status': 'error', 'message': 'Not available'})
    parsed = parse_standard(result, ['FICTION-1', 'FICTION-2'])
    assert len(parsed['observations']) == 1 and len(parsed['errors']) == 1
    bad = parse_standard(response({'currency': 'MYR', 'total_amount': '9'}), ['FICTION-1'])
    assert not bad['observations'] and bad['errors']
    with pytest.raises(ValueError, match='different number'):
        parse_standard(result, ['FICTION-1'])


def test_one_mocked_read_only_post_with_bounded_timeout():
    calls = []

    def transport(req, timeout):
        calls.append((req, timeout))
        return io.BytesIO(json.dumps(response()).encode())

    result = request_standard('fictional-token', [ORDER], CODES, transport=transport)
    assert len(calls) == 1 and calls[0][0].full_url == STANDARD_URL
    assert calls[0][0].get_method() == 'POST' and calls[0][1] == 12
    assert result['environment'] == 'UNKNOWN'
    assert json.loads(calls[0][0].data)['shipment'][0]['sender']['postcode'] == '01000'


def test_rate_limit_and_unverified_environment():
    def throttled(req, timeout):
        raise HTTPError(req.full_url, 429, 'Rate limit', {}, None)
    with pytest.raises(ValueError, match='rate limit'):
        request_standard('fictional-token', [ORDER], CODES, transport=throttled)
    def sandbox_limit(req,timeout):
        body=io.BytesIO(b'{"rate_limit":{"limit_set":"sandbox"}}')
        raise HTTPError(req.full_url,429,'Rate limit',{},body)
    with pytest.raises(ProviderRateLimited) as caught:
        request_standard('fictional-token',[ORDER],CODES,transport=sandbox_limit)
    assert caught.value.provider_environment_evidence=='Sandbox'


def test_response_cannot_be_attributed_to_a_different_order():
    changed=response()
    changed['data'][0]['input']['sender']['postcode']='99999'
    with pytest.raises(ValueError, match='could not be matched'):
        request_standard('fictional-token',[ORDER],CODES,
            transport=lambda req, timeout: io.BytesIO(json.dumps(changed).encode()))


def test_ondemand_preparation_does_not_guess_coordinates_or_call_api():
    assert ONDEMAND_DOCUMENTED_URL.endswith('/ondemand/quotation')
    waypoints = [{'type': 'pickup', 'coordinates': {'latitude': 5.34, 'longitude': 100.28}},
                 {'type': 'dropoff', 'coordinates': {'latitude': 5.32, 'longitude': 100.29}}]
    assert validate_ondemand_waypoints(waypoints)['waypoint'][1]['type'] == 'dropoff'
    with pytest.raises(ValueError, match='latitude and longitude'):
        validate_ondemand_waypoints([waypoints[0], {'type': 'dropoff', 'postcode': '11950'}])


def test_owner_scoped_service_rejects_unverified_or_wrong_account():
    requests = []
    service = OwnerScopedReadOnlyQuoteService(
        lambda identity: {'access_token': 'fictional-token', 'verified_environment': 'UNKNOWN'}
        if identity == 'owner' else None,
        lambda req, timeout: requests.append(req))
    with pytest.raises(ValueError, match='Verified Sandbox'):
        service.quote('owner', 'private-job', [ORDER], CODES, 'one-time-key')
    with pytest.raises(ValueError, match='not connected'):
        service.quote('wrong-owner', 'private-job', [ORDER], CODES, 'one-time-key')
    assert requests == []
