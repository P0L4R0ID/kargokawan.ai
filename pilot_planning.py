"""Deterministic pilot planning from privately stored manual quote evidence.

No provider calls, booking actions, synthetic prices, or recipient data in plans.
"""
import csv
import hashlib
import io
import json
from datetime import datetime
from decimal import Decimal

from hybrid_quotes import FIELDS, normalize, review
from mixed_method import optimize


def fingerprint(orders_json, quote_rows, unavailable_json, job_version):
    raw = json.dumps({'orders': json.loads(orders_json),
                      'quotes': [(qid, json.loads(payload), version) for qid, payload, version in quote_rows],
                      'unavailable': json.loads(unavailable_json), 'job_version': job_version},
                     sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _decode(raw):
    # CSV imports are serialized for storage; restore their field types through
    # the same normalizer used by the existing quotation review workflow.
    values = {}
    for field in FIELDS:
        value = raw.get(field)
        if field == 'shipment_ids' and isinstance(value, (tuple, list)):
            value = ';'.join(str(item) for item in value)
        elif field == 'dropoff_locations' and isinstance(value, list):
            value = json.dumps(value)
        elif isinstance(value, bool):
            value = str(value).lower()
        values[field] = value
    return normalize(values)


def evaluate(orders_json, quote_rows, unavailable_json):
    orders = json.loads(orders_json)
    unavailable = json.loads(unavailable_json)
    quotes = []
    excluded = []
    seen = set()
    for storage_id, payload, _version in quote_rows:
        try:
            raw = json.loads(payload)
            quote = _decode(raw)
            quote_id = quote['quote_id']
            if not quote_id or quote_id in seen:
                raise ValueError('A unique quotation ID is required.')
            seen.add(quote_id)
            # Manually stored evidence can never authenticate its own provider.
            if quote['source_class'] not in ('PUBLIC_REFERENCE', 'USER_IMPORTED_UNVERIFIED'):
                raise ValueError('Manual quotation provenance is not executable.')
            quotes.append(quote)
        except (ValueError, TypeError, KeyError) as exc:
            excluded.append({'storage_id': storage_id, 'status': 'EXCLUDED', 'reason': str(exc)})
    result = optimize(orders, quotes, unavailable, demo=False)
    reviewed = excluded + result['reviewed']
    eligible = [q for q in quotes if review(q, orders)['status'] == 'ELIGIBLE'
                and q['provider'] not in unavailable]
    tasks = []
    for order in orders:
        order_id = str(order['order_id'])
        if not any(order_id in q['shipment_ids'] for q in eligible):
            tasks.append('Collect a complete, valid quotation covering order ' + order_id + '.')
    if result['status'] == 'NOT READY' and not tasks:
        tasks.append('Collect compatible non-overlapping quotations covering every order exactly once.')
    if result['status'] == 'NOT READY':
        return {'status': 'NOT READY', 'reason': result['reason'], 'missing_tasks': tasks,
                'reviewed': reviewed, 'baseline_myr': str(result['baseline_myr']) if result['baseline_myr'] is not None else None}
    decisions = []
    deadlines = {str(order['order_id']): int(order['deadline_days']) for order in orders}
    for item in result['decisions']:
        decision = {key: str(value) if isinstance(value, Decimal) else list(value) if isinstance(value, tuple) else value.isoformat() if isinstance(value, datetime) else value
                    for key, value in item.items()}
        decision['deadlines_days'] = {oid: deadlines[oid] for oid in decision['shipment_ids']}
        decisions.append(decision)
    return {'status': result['status'], 'reason': result['reason'], 'missing_tasks': [],
            'reviewed': reviewed, 'decisions': decisions,
            'total_myr': str(result['total_myr']),
            'baseline_myr': str(result['baseline_myr']) if result['baseline_myr'] is not None else None,
            'difference_myr': str(result['difference_myr']) if result['difference_myr'] is not None else None,
            'provenance': result['claim'], 'booking_status': 'NOT A BOOKING'}


def manifest_csv(job_id, orders, proposal):
    decisions = proposal['decisions']
    output = io.StringIO()
    fields = ['status', 'job_id', 'order_id', 'origin_postcode', 'destination_postcode',
              'deadline_days', 'provider', 'service', 'transport_method', 'quote_id',
              'quoted_group_total_myr', 'source_class', 'source_reference', 'valid_until']
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for order in orders:
        matches = [item for item in decisions if str(order['order_id']) in item['shipment_ids']]
        if len(matches) != 1:
            raise ValueError('Approved plan does not cover each order exactly once.')
        item = matches[0]
        writer.writerow({'status': 'NOT A BOOKING', 'job_id': job_id, 'order_id': order['order_id'],
                         'origin_postcode': order['origin_postcode'],
                         'destination_postcode': order['destination_postcode'],
                         'deadline_days': order['deadline_days'], 'provider': item['provider'],
                         'service': item['service'], 'transport_method': item['method'],
                         'quote_id': item['quote_id'], 'quoted_group_total_myr': item['total_myr'],
                         'source_class': item['source_class'], 'source_reference': item['source_reference'],
                         'valid_until': item['valid_until'].isoformat() if hasattr(item['valid_until'], 'isoformat') else item['valid_until']})
    return output.getvalue()
