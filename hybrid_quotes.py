"""Research observations and future quote normalization. No rate inference or bookings."""
import csv
import io
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

SOURCE_CLASSES={'PUBLIC_REFERENCE','USER_IMPORTED_UNVERIFIED','LIVE_AUTHENTICATED','SYNTHETIC'}
FIELDS='quote_id source_class provider service transport_method origin_postcode destination_postcode pickup_location dropoff_locations shipment_ids physical_weight_kg length_cm width_cm height_cm capacity_kg displayed_cost_myr full_cost tax_status surcharge_status source_reference collected_at valid_until transit_days restrictions'.split()

def template():
    out=io.StringIO(); csv.writer(out).writerow(FIELDS); return out.getvalue()

def parse_csv(data):
    if isinstance(data,bytes): data=data.decode('utf-8-sig')
    reader=csv.DictReader(io.StringIO(data))
    if not reader.fieldnames or set(reader.fieldnames)!=set(FIELDS) or len(reader.fieldnames)!=len(set(reader.fieldnames)): raise ValueError('Research quote CSV columns do not match template.')
    rows=list(reader)
    if not rows: raise ValueError('No research quotes supplied.')
    return [normalize(row) for row in rows]

def normalize(raw):
    row={key:(None if raw.get(key) is None or str(raw.get(key)).strip()=='' else str(raw[key]).strip()) for key in FIELDS}
    if row['source_class'] not in SOURCE_CLASSES: raise ValueError('Unknown quote source class.')
    if not row['provider'] or not row['service'] or not row['source_reference']: raise ValueError('Provider, service and source evidence are required.')
    for key in ('displayed_cost_myr','physical_weight_kg','length_cm','width_cm','height_cm','capacity_kg'):
        if row[key] is not None:
            try: row[key]=Decimal(row[key])
            except InvalidOperation: raise ValueError(f'Invalid {key}.')
            if not row[key].is_finite() or row[key]<0: raise ValueError(f'Invalid {key}.')
    for key in ('collected_at','valid_until'):
        if row[key] is not None:
            try: row[key]=datetime.fromisoformat(row[key].replace('Z','+00:00'))
            except ValueError: raise ValueError(f'Invalid {key}.')
            if row[key].tzinfo is None: raise ValueError(f'{key} requires a time zone.')
    if row['transit_days'] is not None:
        try: row['transit_days']=int(row['transit_days'])
        except ValueError: raise ValueError('Invalid transit_days.')
    if row['full_cost'] not in (None,'true','false'): raise ValueError('full_cost must be true or false.')
    row['full_cost']=row['full_cost']=='true'
    row['shipment_ids']=tuple(x.strip() for x in row['shipment_ids'].split(';')) if row['shipment_ids'] else ()
    if row['dropoff_locations']:
        try: row['dropoff_locations']=json.loads(row['dropoff_locations'])
        except ValueError: raise ValueError('dropoff_locations must be JSON.')
        if not isinstance(row['dropoff_locations'],list) or any(not isinstance(x,dict) or not x.get('shipment_id') or not x.get('postcode') or not isinstance(x.get('sequence'),int) for x in row['dropoff_locations']): raise ValueError('Invalid drop-off locations.')
    else: row['dropoff_locations']=[]
    return row

def review(row,orders=(),now=None):
    now=now or datetime.now(timezone.utc)
    missing=[]
    for key in ('quote_id','origin_postcode','destination_postcode','pickup_location','shipment_ids','physical_weight_kg','length_cm','width_cm','height_cm','displayed_cost_myr','tax_status','surcharge_status','collected_at','valid_until','transit_days','restrictions'):
        if row[key] is None or row[key]==(): missing.append(key)
    if row['transport_method']=='multi_stop_vehicle':
        if not row['dropoff_locations']: missing.append('dropoff_locations')
        if row['capacity_kg'] is None: missing.append('capacity_kg')
    if row['valid_until'] is not None and row['valid_until']<=now: return {'status':'EXPIRED','missing':missing,'reason':'Quote validity ended.'}
    if row['source_class']=='PUBLIC_REFERENCE': return {'status':'INCOMPLETE','missing':missing,'reason':'Public reference is not a shipment quotation.'}
    if missing: return {'status':'INCOMPLETE','missing':missing,'reason':'Required evidence is missing.'}
    if not row['full_cost'] or row['displayed_cost_myr']<=0 or row['tax_status']!='included' or row['surcharge_status']!='included' or row['restrictions'].lower()!='none' or row['transit_days']<=0: return {'status':'NEEDS_REVIEW','missing':[],'reason':'Full final cost and charge treatment are unconfirmed.'}
    if len(set(row['shipment_ids']))!=len(row['shipment_ids']) or any(not re.fullmatch(r'\d{5}',row[k]) for k in ('origin_postcode','destination_postcode')): return {'status':'INELIGIBLE','missing':[],'reason':'Invalid coverage or postcode.'}
    if row['transport_method']=='multi_stop_vehicle' and (len(row['dropoff_locations'])!=len(row['shipment_ids']) or sorted(x['sequence'] for x in row['dropoff_locations'])!=list(range(1,len(row['shipment_ids'])+1)) or any(not re.fullmatch(r'\d{5}',str(x['postcode'])) for x in row['dropoff_locations']) or {x['shipment_id'] for x in row['dropoff_locations']}!=set(row['shipment_ids'])): return {'status':'INELIGIBLE','missing':[],'reason':'Stops do not cover all shipments exactly once.'}
    by_id={str(x['order_id']):x for x in orders}
    if set(row['shipment_ids'])-set(by_id): return {'status':'NEEDS_REVIEW','missing':[],'reason':'Shipment orders are needed to confirm coverage.'}
    if orders:
        if row['capacity_kg'] is not None and sum(Decimal(str(by_id[x]['weight_kg'])) for x in row['shipment_ids'])>row['capacity_kg']: return {'status':'INELIGIBLE','missing':[],'reason':'Vehicle capacity exceeded.'}
        if any(int(by_id[x]['deadline_days'])<row['transit_days'] or str(by_id[x]['origin_postcode'])!=row['origin_postcode'] for x in row['shipment_ids']): return {'status':'INELIGIBLE','missing':[],'reason':'Pickup or deadline mismatch.'}
        if row['transport_method']=='multi_stop_vehicle':
            stops={x['shipment_id']:x['postcode'] for x in row['dropoff_locations']}
            if any(str(by_id[x]['destination_postcode'])!=stops[x] for x in row['shipment_ids']): return {'status':'INELIGIBLE','missing':[],'reason':'Delivery stop mismatch.'}
        elif len(row['shipment_ids'])!=1 or str(by_id[row['shipment_ids'][0]]['destination_postcode'])!=row['destination_postcode']: return {'status':'INELIGIBLE','missing':[],'reason':'Destination or shipment mismatch.'}
    return {'status':'ELIGIBLE','missing':[],'reason':'Complete quoted cost and route confirmed against supplied orders.'}
