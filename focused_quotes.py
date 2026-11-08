"""Two-provider, evidence-based comparison; no network requests or bookings."""
import csv
import io
import json
import hashlib
from decimal import Decimal
from hybrid_quotes import FIELDS, normalize, review

PROVIDERS=('EasyParcel Malaysia','Lalamove Malaysia')

def template(provider):
    if provider not in PROVIDERS: raise ValueError('Unsupported provider.')
    out=io.StringIO(); writer=csv.writer(out); writer.writerow(FIELDS); return out.getvalue()

def import_provider(provider,data):
    if provider not in PROVIDERS: raise ValueError('Unsupported provider.')
    if isinstance(data,bytes): data=data.decode('utf-8-sig')
    reader=csv.DictReader(io.StringIO(data))
    if not reader.fieldnames or set(reader.fieldnames)!=set(FIELDS): raise ValueError('Use the provider quote CSV template.')
    rows=[]
    for raw in reader:
        if raw.get('provider')!=provider: raise ValueError('Quote provider does not match upload.')
        row=normalize(raw)
        if row['source_class']=='LIVE_AUTHENTICATED':
            row['source_class']='USER_IMPORTED_UNVERIFIED'
        if provider=='EasyParcel Malaysia' and row['transport_method']!='parcel_courier': raise ValueError('EasyParcel import is for parcel courier quotes.')
        if provider=='Lalamove Malaysia' and row['transport_method']!='multi_stop_vehicle': raise ValueError('Lalamove import needs an explicit vehicle route.')
        rows.append(row)
    if not rows: raise ValueError('No provider quotations supplied.')
    return rows

def _orders(orders):
    data=orders.to_dict('records') if hasattr(orders,'to_dict') else list(orders)
    if not data or len({str(x['order_id']) for x in data})!=len(data): raise ValueError('Orders must have unique IDs.')
    return data

def evaluate(orders,courier_quotes,vehicle_quotes):
    data=_orders(orders); ids={str(x['order_id']) for x in data}
    courier_reviews=[(q,review(q,data)) for q in courier_quotes]
    vehicle_reviews=[(q,review(q,data)) for q in vehicle_quotes]
    couriers={}
    for oid in ids:
        choices=[q for q,r in courier_reviews if r['status']=='ELIGIBLE' and q['source_class']!='SYNTHETIC' and q['shipment_ids']==(oid,)]
        if choices: couriers[oid]=min(choices,key=lambda q:q['displayed_cost_myr'])
    courier_total=sum((q['displayed_cost_myr'] for q in couriers.values()),Decimal(0)) if len(couriers)==len(ids) else None
    vehicles=[q for q,r in vehicle_reviews if r['status']=='ELIGIBLE' and q['source_class']!='SYNTHETIC' and set(q['shipment_ids'])==ids and len(q['shipment_ids'])==len(ids)]
    vehicle=min(vehicles,key=lambda q:q['displayed_cost_myr']) if vehicles else None
    comparable=courier_total is not None and vehicle is not None
    return {'status':'COMPARABLE' if comparable else 'NOT READY','courier_total_myr':courier_total,'vehicle_total_myr':vehicle['displayed_cost_myr'] if vehicle else None,
        'difference_myr':courier_total-vehicle['displayed_cost_myr'] if comparable else None,
        'courier_quotes':couriers,'vehicle_quote':vehicle,
        'reviews':[{'provider':q['provider'],'quote_id':q['quote_id'],'source_class':q['source_class'],'displayed_cost_myr':q['displayed_cost_myr'],**r} for q,r in courier_reviews+vehicle_reviews]}

def fingerprint(orders,courier_quotes,vehicle_quotes):
    data=_orders(orders)
    raw=repr(data)+repr(courier_quotes)+repr(vehicle_quotes)
    return hashlib.sha256(raw.encode()).hexdigest()

def preview(orders,courier_quotes,vehicle_quotes):
    result=evaluate(orders,courier_quotes,vehicle_quotes)
    if result['status']!='COMPARABLE': raise ValueError('NOT READY: complete matching courier and vehicle quotes are required.')
    return {'fingerprint':fingerprint(orders,courier_quotes,vehicle_quotes),'comparison':result}

def approve(proposal,orders,courier_quotes,vehicle_quotes):
    if proposal['fingerprint']!=fingerprint(orders,courier_quotes,vehicle_quotes): raise ValueError('Inputs changed; generate a fresh comparison.')
    current=preview(orders,courier_quotes,vehicle_quotes)['comparison']
    return current
