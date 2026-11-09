"""Read-only EasyParcel Open API 2026-09 quotation boundary.

Contract: EasyParcel API Reference.pdf (2026-09), pp. 28-31, 39-43, 80-85.
Transport is injected; importing this module never contacts a provider. Returned
observations are review-only and cannot enter the mixed-method optimiser.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import re
from urllib import request, error

STANDARD_URL = 'https://api.easyparcel.com/open_api/2026-09/shipment/quotations'
ONDEMAND_DOCUMENTED_URL = 'https://api.easyparcel.com/open_api/2026-09/ondemand/quotation'
MAX_SHIPMENTS = 5


class ProviderRateLimited(ValueError):
    def __init__(self, environment=None):
        super().__init__('EasyParcel rate limit reached; try again later.')
        self.provider_environment_evidence = environment


def _positive(value, name):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(name + ' must be a positive number.') from None
    if not number.is_finite() or number <= 0:
        raise ValueError(name + ' must be a positive number.')
    return number


def _money(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return str(amount) if amount.is_finite() and amount >= 0 else None


def _location(postcode, subdivision):
    if not isinstance(postcode, str) or not re.fullmatch(r'\d{5}', postcode):
        raise ValueError('An exact five-digit postcode is required.')
    if not isinstance(subdivision, str) or not re.fullmatch(r'MY-\d{2}', subdivision):
        raise ValueError('An explicitly supplied Malaysian ISO 3166 subdivision code is required.')
    return {'postcode': postcode, 'subdivision_code': subdivision, 'country': 'MY'}


def standard_payload(orders, subdivisions):
    """Use only known order fields; subdivision codes must be supplied explicitly."""
    if not isinstance(orders, list) or not 1 <= len(orders) <= MAX_SHIPMENTS:
        raise ValueError('Select one to five orders.')
    if not isinstance(subdivisions, dict):
        raise ValueError('Verified subdivision codes are required.')
    shipments = []
    for order in orders:
        order_id = order['order_id']
        codes = subdivisions.get(order_id)
        if not isinstance(codes, dict):
            raise ValueError('Missing subdivision codes for order ' + str(order_id) + '.')
        item = {
            'sender': _location(order.get('origin_postcode'), codes.get('sender')),
            'receiver': _location(order.get('destination_postcode'), codes.get('receiver')),
            'weight': float(_positive(order.get('weight_kg'), 'Weight')),
        }
        for source, target in (('width_cm', 'width'), ('length_cm', 'length'), ('height_cm', 'height')):
            if order.get(source) not in (None, ''):
                item[target] = float(_positive(order[source], target))
        shipments.append(item)
    # No coupon or BYOC overrides: retain the account's configured behaviour.
    return {'shipment': shipments}


def parse_standard(response, order_ids, collected_at=None, environment=None):
    """Preserve partial failures and unknown fields without inventing eligibility."""
    if not isinstance(response, dict) or not isinstance(response.get('data'), list):
        raise ValueError('Malformed provider quotation response.')
    if len(response['data']) != len(order_ids):
        raise ValueError('Provider returned a different number of shipment results.')
    collected_at = collected_at or datetime.now(timezone.utc).isoformat()
    observations, errors = [], []
    for order_id, item in zip(order_ids, response['data']):
        if not isinstance(item, dict) or item.get('status') != 'success':
            errors.append({'order_id': order_id, 'reason': 'Provider reported a shipment error.'})
            continue
        if not isinstance(item.get('quotations'), list):
            errors.append({'order_id': order_id, 'reason': 'Provider omitted quotations.'})
            continue
        for quotation in item['quotations']:
            if not isinstance(quotation, dict):
                continue
            courier, pricing = quotation.get('courier'), quotation.get('pricing')
            if not isinstance(courier, dict) or not isinstance(pricing, dict):
                continue
            total = _money(pricing.get('total_amount'))
            payable = _money(pricing.get('seller_payable_amount'))
            if pricing.get('currency') != 'MYR' or total is None or payable is None:
                errors.append({'order_id': order_id, 'reason': 'Quote lacks complete MYR pricing.'})
                continue
            observations.append({
                'order_id': order_id, 'source_class': 'LIVE_AUTHENTICATED',
                'review_status': 'NEEDS_REVIEW', 'planner_eligible': False,
                'environment': environment or 'UNKNOWN',
                'request_id': response.get('request_id'),
                'service_id': courier.get('service_id'), 'service_name': courier.get('service_name'),
                'courier_id': courier.get('courier_id'), 'courier_name': courier.get('courier_name'),
                'delivery_duration': courier.get('delivery_duration'),
                'total_amount_myr': total, 'seller_payable_amount_myr': payable,
                'is_byoc_or_split_payable': Decimal(payable) != Decimal(total),
                'pricing': {key: _money(pricing.get(key)) for key in (
                    'shipment_price', 'shipment_tax', 'total_features_price', 'total_features_tax',
                    'byoc_charges', 'byoc_charges_tax', 'coupon_discount')},
                'coupon_applied': pricing.get('auto_apply_coupon'),
                'collected_at': collected_at, 'source_reference': STANDARD_URL,
                'valid_until': None,
                'review_reason': 'Expiry, conditions and deadline compatibility require separate review.',
            })
    return {'observations': observations, 'errors': errors,
            'request_id': response.get('request_id'), 'environment': environment or 'UNKNOWN'}


def request_standard(access_token, orders, subdivisions, *, transport, timeout=12):
    """Exactly one bounded, caller-triggered read-only POST; no retry or side effect."""
    if not access_token or not isinstance(access_token, str):
        raise ValueError('Server-side access token required.')
    payload = standard_payload(orders, subdivisions)
    req = request.Request(STANDARD_URL, data=json.dumps(payload).encode(), method='POST', headers={
        'Authorization': 'Bearer ' + access_token, 'Content-Type': 'application/json',
        'Accept': 'application/json'})
    try:
        with transport(req, timeout=timeout) as response:
            result = json.load(response)
    except error.HTTPError as exc:
        if exc.code == 429:
            try:
                details = json.loads(exc.read(4096))
                limit_set = details.get('rate_limit', {}).get('limit_set')
            except (ValueError, TypeError, AttributeError, OSError):
                limit_set = None
            environment = {'sandbox':'Sandbox','live':'Live'}.get(str(limit_set).lower())
            raise ProviderRateLimited(environment) from None
        raise ValueError('EasyParcel quotation request failed (HTTP ' + str(exc.code) + ').') from None
    except (error.URLError, TimeoutError, OSError):
        raise ValueError('EasyParcel quotation request timed out or was unavailable.') from None
    if not isinstance(result, dict) or result.get('status_code') != 200:
        raise ValueError('EasyParcel rejected the quotation request.')
    rows = result.get('data')
    if not isinstance(rows, list) or len(rows) != len(payload['shipment']):
        raise ValueError('EasyParcel returned an incomplete shipment batch.')
    for expected, returned in zip(payload['shipment'], rows):
        echoed = returned.get('input') if isinstance(returned, dict) else None
        if not isinstance(echoed, dict) or any(echoed.get(field) != expected[field]
                for field in ('sender', 'receiver', 'weight')):
            raise ValueError('EasyParcel shipment response could not be matched to the requested order.')
    # The standard success schema does not attest the account environment.
    # A caller-selected label must never be presented as provider verification.
    parsed = parse_standard(result, [order['order_id'] for order in orders])
    limit_set = result.get('rate_limit', {}).get('limit_set') if isinstance(result.get('rate_limit'), dict) else None
    parsed['provider_environment_evidence'] = {'sandbox':'Sandbox','live':'Live'}.get(
        str(limit_set).lower())
    return parsed


def validate_ondemand_waypoints(waypoints):
    """Prepare exact ordered coordinates; on-demand requests remain disabled."""
    if not isinstance(waypoints, list) or len(waypoints) < 2 or len(waypoints) > 6:
        raise ValueError('At least one pickup and one drop-off with exact coordinates are required.')
    if waypoints[0].get('type') != 'pickup' or any(item.get('type') != 'dropoff' for item in waypoints[1:]):
        raise ValueError('Ordered route must start at pickup and include explicit drop-offs.')
    result = []
    for item in waypoints:
        coordinates = item.get('coordinates')
        if not isinstance(coordinates, dict):
            raise ValueError('Verified latitude and longitude are required for every stop.')
        try:
            latitude = Decimal(str(coordinates['latitude']))
            longitude = Decimal(str(coordinates['longitude']))
        except (KeyError, TypeError, InvalidOperation, ValueError):
            raise ValueError('Invalid stop coordinates.') from None
        if not latitude.is_finite() or not longitude.is_finite() or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError('Invalid stop coordinates.')
        result.append({'type': item['type'], 'coordinates': {
            'latitude': float(latitude), 'longitude': float(longitude)}})
    return {'waypoint': result}


class OwnerScopedReadOnlyQuoteService:
    """Server-side adapter for an owner-verified token repository.

    The production backend does not construct this service until persistent,
    encrypted owner-scoped OAuth storage and account verification are complete.
    The lookup must verify the signed operator token itself; no browser-supplied
    account ID, token or environment is accepted here.
    """

    def __init__(self, token_lookup, transport):
        self._token_lookup = token_lookup
        self._transport = transport

    def quote(self, identity_token, job_id, orders, subdivisions, request_key):
        connection = self._token_lookup(identity_token)
        if not isinstance(connection, dict) or not connection.get('access_token'):
            raise ValueError('EasyParcel account is not connected.')
        # Account verification is a strict precondition. A user-entered
        # Sandbox/Live label is not evidence of the linked account environment.
        if connection.get('verified_environment') != 'Sandbox':
            raise ValueError('Verified Sandbox account connection is required.')
        result = request_standard(connection['access_token'], orders, subdivisions,
                                  transport=self._transport)
        result['environment'] = 'Sandbox'
        for observation in result['observations']:
            observation['environment'] = 'Sandbox'
        return result
