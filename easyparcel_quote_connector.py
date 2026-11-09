"""Disconnected EasyParcel Open API boundary and test-only rate observations.

The Open API OAuth quotation route/response contract is not yet verified. This
module performs no network I/O and cannot create planner-eligible real quotes.
"""
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json

from hybrid_quotes import review
from pilot_planning import _decode


REQUIRED_ORDER_FACTS = ('order_id', 'origin_postcode', 'destination_postcode',
                        'weight_kg', 'length_cm', 'width_cm', 'height_cm')
TEST_ENDPOINT = 'TEST_ONLY_INTERNAL_FIXTURE_NOT_A_PROVIDER_ENDPOINT'


def missing_shipment_facts(order):
    if not isinstance(order, dict):
        return list(REQUIRED_ORDER_FACTS)
    missing = [field for field in REQUIRED_ORDER_FACTS if order.get(field) is None or str(order[field]).strip() == '']
    for field in ('origin_postcode', 'destination_postcode'):
        if field not in missing and not re.fullmatch(r'\d{5}', str(order[field])):
            missing.append(field + ' (five-digit postcode required)')
    for field in ('weight_kg', 'length_cm', 'width_cm', 'height_cm'):
        if field not in missing:
            try:
                value = Decimal(str(order[field]))
            except (InvalidOperation, TypeError, ValueError):
                value = None
            if value is None or not value.is_finite() or value <= 0:
                missing.append(field + ' (positive number required)')
    return missing


class QuoteAcquisitionAdapter(ABC):
    @abstractmethod
    def connection_status(self):
        """Return a truthful connection status without exposing credentials."""

    @abstractmethod
    def request_rates(self, orders):
        """Return observations and rejections; never book or pay."""


class EasyParcelOpenApiQuoteAdapter(QuoteAcquisitionAdapter):
    """Production boundary. The verified OAuth rate contract is not implemented."""
    def __init__(self, env=None):
        self.env = env if env is not None else os.environ

    def connection_status(self):
        enabled = self.env.get('EASYPARCEL_QUOTE_CONNECTOR_ENABLED') == '1'
        return {'status': 'NOT_CONNECTED', 'credential_status': 'UNAVAILABLE',
                'reason': ('Connector is disabled on the server.' if not enabled else
                           'OAuth account linking, safe token storage and the Open API rate contract are unverified.')}

    def request_rates(self, orders):
        return {**self.connection_status(), 'observations': [], 'rejections': [],
                'missing_by_order': {str(order.get('order_id', '<unknown>')): missing_shipment_facts(order)
                                     for order in orders}}


def interpret_test_fixture(payload, order, *, transport_label=TEST_ENDPOINT):
    """Parse an internal mock schema, never a claimed EasyParcel API response."""
    missing = missing_shipment_facts(order)
    if missing:
        return {'status': 'MISSING_SHIPMENT_DATA', 'observations': [], 'rejections': [],
                'missing_fields': missing}
    if transport_label != TEST_ENDPOINT:
        raise ValueError('Only the internal test fixture contract is supported.')
    if not isinstance(payload, dict) or payload.get('test_fixture') is not True:
        return {'status': 'UNTRUSTED_RESPONSE', 'observations': [],
                'rejections': [{'reason': 'Response is not an explicitly marked test fixture.'}], 'missing_fields': []}
    if payload.get('transport_error'):
        return {'status': 'TRANSPORT_ERROR', 'observations': [],
                'rejections': [{'reason': 'Synthetic transport failure; no provider was contacted.'}], 'missing_fields': []}
    if payload.get('authentication_error'):
        return {'status': 'AUTHENTICATION_ERROR', 'observations': [],
                'rejections': [{'reason': 'Synthetic authentication failure; no provider was contacted.'}], 'missing_fields': []}
    services = payload.get('services')
    if not isinstance(services, list):
        return {'status': 'INVALID_RESPONSE', 'observations': [],
                'rejections': [{'reason': 'Test fixture needs a services list.'}], 'missing_fields': []}
    if not services:
        return {'status': 'NO_SERVICES', 'observations': [], 'rejections': [], 'missing_fields': []}
    observed, rejected = [], []
    for index, item in enumerate(services):
        if not isinstance(item, dict):
            rejected.append({'index': index, 'reason': 'Service record is not an object.'})
            continue
        service_id, service = item.get('service_id'), item.get('service_name')
        if not isinstance(service_id, str) or not service_id.strip() or not isinstance(service, str) or not service.strip():
            rejected.append({'index': index, 'reason': 'Service identifier and name are required.'})
            continue
        def amount(name):
            if item.get(name) is None:
                return None
            try:
                value = Decimal(str(item[name]))
            except (InvalidOperation, ValueError, TypeError):
                return None
            return value if value.is_finite() and value >= 0 else None
        price = amount('displayed_cost_myr')
        if price is None or not price.is_finite() or price <= 0:
            rejected.append({'index': index, 'reason': 'A positive displayed price is required.'})
            continue
        if item.get('currency') != 'MYR':
            rejected.append({'index': index, 'reason': 'Only explicit MYR observations are supported.'})
            continue
        components = {name: amount(name) for name in ('tax_myr', 'surcharge_myr', 'total_payable_myr')}
        if any(item.get(name) is not None and components[name] is None for name in components):
            rejected.append({'index': index, 'reason': 'A disclosed monetary component is invalid.'})
            continue
        try:
            quoted_at = datetime.fromisoformat(str(item['quoted_at']).replace('Z', '+00:00')) if item.get('quoted_at') else None
            valid_until = datetime.fromisoformat(str(item['valid_until']).replace('Z', '+00:00')) if item.get('valid_until') else None
            if any(value is not None and value.tzinfo is None for value in (quoted_at, valid_until)):
                raise ValueError('Timestamps require a time zone.')
        except ValueError:
            rejected.append({'index': index, 'reason': 'Quotation timestamp or validity is invalid.'})
            continue
        transit = item.get('transit_days')
        if transit is not None and (isinstance(transit, bool) or not isinstance(transit, int) or transit <= 0):
            rejected.append({'index': index, 'reason': 'Explicit transit days must be a positive integer.'})
            continue
        missing_evidence = [label for name, label in (('total_payable_myr', 'all-in payable total'),
            ('tax_myr', 'tax treatment'), ('surcharge_myr', 'surcharge treatment'),
            ('valid_until', 'quote validity'), ('transit_days', 'delivery deadline evidence'))
            if (components.get(name) if name in components else valid_until if name == 'valid_until' else transit) is None]
        observed.append({
            'pilot_job_id': None, 'covered_order_ids': [str(order['order_id'])],
            'provider': 'EasyParcel Malaysia', 'service_id': service_id, 'service': service,
            'origin_postcode': str(order['origin_postcode']),
            'destination_postcode': str(order['destination_postcode']),
            'physical_weight_kg': str(order['weight_kg']),
            'length_cm': str(order['length_cm']), 'width_cm': str(order['width_cm']),
            'height_cm': str(order['height_cm']), 'displayed_cost_myr': str(price),
            'currency': 'MYR', 'tax_myr': str(components['tax_myr']) if components['tax_myr'] is not None else None,
            'surcharge_myr': str(components['surcharge_myr']) if components['surcharge_myr'] is not None else None,
            'total_payable_myr': str(components['total_payable_myr']) if components['total_payable_myr'] is not None else None,
            'source_endpoint': TEST_ENDPOINT,
            'source_reference': 'TEST_ONLY — synthetic internal response',
            'collected_at': datetime.now(timezone.utc).isoformat(),
            'quoted_at': quoted_at.isoformat() if quoted_at else None,
            'valid_until': valid_until.isoformat() if valid_until else None,
            'transit_days': transit, 'delivery_text': item.get('delivery_text'),
            'restrictions': item.get('restrictions'),
            'transit_guaranteed': None, 'full_cost': False, 'source_class': 'SYNTHETIC',
            'review_status': 'INCOMPLETE', 'missing_fields': missing_evidence,
            'exclusion_reason': 'TEST_ONLY synthetic observation; never eligible for real planning.'})
    return {'status': 'TEST_ONLY' if observed else 'INVALID_RESPONSE',
            'observations': observed, 'rejections': rejected, 'missing_fields': []}


class FixtureEasyParcelQuoteAdapter(QuoteAcquisitionAdapter):
    """In-memory synthetic transport for tests and an explicitly labelled UI preview."""
    def __init__(self, transport):
        self.transport = transport

    def connection_status(self):
        return {'status': 'TEST_ONLY', 'credential_status': 'NOT_USED',
                'reason': 'Internal fixture only; no EasyParcel request or authentication.'}

    def request_rates(self, orders):
        rows = []
        rejections = []
        for order in orders:
            if missing_shipment_facts(order):
                rejections.append({'order_id': str(order.get('order_id', '<unknown>')),
                                   'reason': 'Required shipment facts are missing.'})
                continue
            try:
                result = interpret_test_fixture(self.transport(order), order)
            except (OSError, TimeoutError, ValueError):
                result = {'status': 'TRANSPORT_ERROR', 'observations': [],
                          'rejections': [{'reason': 'Synthetic transport failed.'}]}
            rows.extend(result['observations'])
            rejections.extend({'order_id': str(order['order_id']), **item} for item in result['rejections'])
        return {**self.connection_status(), 'observations': rows, 'rejections': rejections}


def synthetic_demo_transport(_order):
    return {'test_fixture': True, 'services': [
        {'service_id': 'TEST-SERVICE-ONLY', 'service_name': 'Synthetic parcel illustration',
         'displayed_cost_myr': '17.25', 'currency': 'MYR'}]}


def manual_quote_readiness(job_id, orders, quote_rows, unavailable=()):
    """Owner-scoped rows are supplied by the store; this function never fetches rates."""
    previews = []
    covered = set()
    seen = set()
    for storage_id, payload, _version in quote_rows:
        try:
            item = _decode(json.loads(payload))
            if item['provider'] != 'EasyParcel Malaysia':
                continue
            quote_id = item['quote_id']
            if not quote_id or quote_id in seen:
                raise ValueError('Duplicate or missing quotation ID.')
            seen.add(quote_id)
            verdict = review(item, orders)
            if item['transport_method'] != 'parcel_courier':
                verdict = {'status': 'INELIGIBLE', 'missing': [],
                           'reason': 'EasyParcel courier evidence must cover one parcel order.'}
            if item['source_class'] != 'USER_IMPORTED_UNVERIFIED' and verdict['status'] == 'ELIGIBLE':
                verdict = {'status': 'INELIGIBLE', 'missing': [],
                           'reason': 'Only complete user-supplied courier quotes can enter real planning.'}
            if item['provider'] in unavailable and verdict['status'] == 'ELIGIBLE':
                verdict = {'status': 'INELIGIBLE', 'missing': [],
                           'reason': 'Provider is marked unavailable for this job.'}
            if verdict['status'] == 'ELIGIBLE':
                covered.update(item['shipment_ids'])
            previews.append({'storage_id': storage_id, 'quote_id': quote_id,
                             'provider': item['provider'], 'service': item['service'],
                             'covered_order_ids': list(item['shipment_ids']),
                             'source_class': item['source_class'],
                             'source_reference': item['source_reference'],
                             'displayed_cost_myr': str(item['displayed_cost_myr']) if item['displayed_cost_myr'] is not None else None,
                             'currency': 'MYR' if item['displayed_cost_myr'] is not None else None,
                             'full_cost': item['full_cost'], 'tax_status': item['tax_status'],
                             'surcharge_status': item['surcharge_status'],
                             'collected_at': item['collected_at'].isoformat() if item['collected_at'] is not None else None,
                             'valid_until': item['valid_until'].isoformat() if item['valid_until'] is not None else None,
                             'status': verdict['status'], 'reason': verdict['reason'],
                             'missing_fields': verdict['missing']})
        except (ValueError, TypeError, KeyError) as exc:
            previews.append({'storage_id': storage_id, 'status': 'INELIGIBLE',
                             'reason': str(exc), 'missing_fields': []})
    missing = [{'order_id': str(order['order_id']),
                'action': 'Obtain a complete, valid EasyParcel parcel quotation with all-in MYR payable amount, tax and surcharge treatment, expiry, transit evidence and source reference.'}
               for order in orders if str(order['order_id']) not in covered]
    return {'pilot_job_id': job_id, 'connector': EasyParcelOpenApiQuoteAdapter().connection_status(),
            'manual_quote_previews': previews, 'missing_quote_tasks': missing,
            'evidence_note': 'Manual quotes are USER_IMPORTED_UNVERIFIED; no Open API call was made.'}
