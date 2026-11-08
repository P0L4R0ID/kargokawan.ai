"""Quote request preparation and reviewed manual quote drafts; no carrier calls."""
import json
from datetime import datetime, timezone
from decimal import Decimal
from engine import CITIES
from hybrid_quotes import normalize, review
from mixed_method import optimize

PROVIDERS=('EasyParcel Malaysia','Lalamove Malaysia')

def request_checklist(orders):
    rows=orders.to_dict('records') if hasattr(orders,'to_dict') else list(orders)
    tasks=[]
    for row in rows:
        oid=str(row.get('order_id','')).strip()
        for field in ('origin_postcode','destination_postcode','weight_kg','length_cm','width_cm','height_cm','deadline_days'):
            if row.get(field) is None or str(row.get(field)).strip()=='': tasks.append(f'{oid}: supply {field} before requesting a quote')
        tasks.append(f'{oid}: request full payable EasyParcel courier quote with service, transit, taxes, surcharges, restrictions, timestamp, expiry and provider reference')
    return tasks

def request_details(orders):
    rows=orders.to_dict('records') if hasattr(orders,'to_dict') else list(orders)
    keys=('order_id','origin','destination','origin_postcode','destination_postcode','weight_kg','length_cm','width_cm','height_cm','deadline_days')
    return [{key:row.get(key,'') for key in keys} for row in rows]

def vehicle_candidates(orders):
    rows=orders.to_dict('records') if hasattr(orders,'to_dict') else list(orders)
    groups={}
    for row in rows:
        if row.get('origin') not in CITIES or row.get('destination') not in CITIES: continue
        region=CITIES[row['destination']]
        if region!=CITIES[row['origin']]: continue
        key=(row.get('origin_postcode'),region)
        groups.setdefault(key,[]).append(row)
    return [{'origin_postcode':postcode,'region':region,'shipment_ids':[str(row['order_id']) for row in group],
             'stops':[{'sequence':i,'shipment_id':str(row['order_id']),'postcode':str(row.get('destination_postcode',''))} for i,row in enumerate(group,1)],
             'caution':'REQUEST CANDIDATE ONLY: provider availability and route feasibility are unverified.'}
            for (postcode,region),group in groups.items() if postcode and len(group)>=2 and all(str(row.get('destination_postcode','')).isdigit() and len(str(row.get('destination_postcode','')))==5 for row in group)]

def make_draft(fields):
    raw=dict(fields)
    raw['source_class']='USER_IMPORTED_UNVERIFIED'
    raw['collected_at']=raw.get('collected_at') or datetime.now(timezone.utc).isoformat()
    raw['dropoff_locations']=json.dumps(raw['dropoff_locations']) if isinstance(raw.get('dropoff_locations'),list) else raw.get('dropoff_locations','')
    raw['shipment_ids']=';'.join(raw['shipment_ids']) if isinstance(raw.get('shipment_ids'),(list,tuple)) else raw.get('shipment_ids','')
    return normalize(raw)

def revise_draft(draft,changes):
    raw={key:value for key,value in draft.items()}
    raw.update(changes)
    for key in ('collected_at','valid_until'):
        if hasattr(raw.get(key),'isoformat'): raw[key]=raw[key].isoformat()
    raw['displayed_cost_myr']=str(raw['displayed_cost_myr']) if raw.get('displayed_cost_myr') is not None else ''
    for key in ('physical_weight_kg','length_cm','width_cm','height_cm','capacity_kg'):
        if raw.get(key) is not None: raw[key]=str(raw[key])
    raw['full_cost']='true' if raw.get('full_cost') else 'false'
    return make_draft(raw)

def collection_progress(orders,quotes,unavailable=()):
    rows=orders.to_dict('records') if hasattr(orders,'to_dict') else list(orders)
    reviews=[review(q,rows) for q in quotes]
    eligible_courier={str(x['order_id']):[] for x in rows}
    vehicles=[]
    for quote,result in zip(quotes,reviews):
        if result['status']!='ELIGIBLE' or quote['source_class'] not in ('USER_IMPORTED_UNVERIFIED','LIVE_AUTHENTICATED') or quote['provider'] in unavailable: continue
        if quote['transport_method']=='parcel_courier' and len(quote['shipment_ids'])==1:
            eligible_courier.get(quote['shipment_ids'][0],[]).append(quote['quote_id']) if quote['shipment_ids'][0] in eligible_courier else None
        elif quote['transport_method']=='multi_stop_vehicle': vehicles.append({'quote_id':quote['quote_id'],'shipment_ids':quote['shipment_ids']})
    plan=optimize(orders,quotes,unavailable)
    missing=[f'{oid}: obtain a complete eligible courier quote' for oid,ids in eligible_courier.items() if not ids]
    if plan['status']=='NOT READY': missing.append('Obtain enough compatible full-cost quotes to cover every order exactly once.')
    return {'courier_by_order':eligible_courier,'vehicle_subsets':vehicles,'reviews':[{'quote_id':q['quote_id'],'status':r['status'],'missing':r['missing'],'reason':r['reason']} for q,r in zip(quotes,reviews)],'plan':plan,'next_actions':missing}


def order_facts(orders, shipment_ids):
    """Copy shipment facts only; these are not provider-confirmed limits."""
    rows=orders.to_dict('records') if hasattr(orders,'to_dict') else list(orders)
    selected=[row for row in rows if str(row.get('order_id')) in shipment_ids]
    if len(selected)!=len(set(shipment_ids)) or not selected:
        raise ValueError('Select existing unique order IDs from the delivery job.')
    origins={str(row.get('origin_postcode','')) for row in selected}
    if len(origins)!=1 or not next(iter(origins)):
        raise ValueError('Selected orders need one explicit pickup postcode.')
    return {'shipment_ids':[str(row['order_id']) for row in selected],
            'origin_postcode':next(iter(origins)),
            'destination_postcode':str(selected[0].get('destination_postcode','')),
            'physical_weight_kg':sum(Decimal(str(row['weight_kg'])) for row in selected),
            'max_order_length_cm':max(Decimal(str(row['length_cm'])) for row in selected),
            'max_order_width_cm':max(Decimal(str(row['width_cm'])) for row in selected),
            'max_order_height_cm':max(Decimal(str(row['height_cm'])) for row in selected),
            'stops':[{'sequence':i,'shipment_id':str(row['order_id']),'postcode':str(row.get('destination_postcode',''))} for i,row in enumerate(selected,1)]}


def malaysia_timestamp(day,clock):
    """Convert date/time controls to an aware Malaysia-local instant."""
    from datetime import datetime, date, time
    from zoneinfo import ZoneInfo
    if not isinstance(day,date) or not isinstance(clock,time):
        raise ValueError('Choose a valid local date and time.')
    return datetime.combine(day,clock).replace(tzinfo=ZoneInfo('Asia/Kuala_Lumpur'))


def missing_quote_actions(quote,orders):
    result=review(quote,orders)
    labels={'valid_until':'quote expiry','tax_status':'tax treatment','surcharge_status':'surcharge treatment','source_reference':'provider evidence reference',
            'length_cm':'provider-confirmed eligible length','width_cm':'provider-confirmed eligible width','height_cm':'provider-confirmed eligible height',
            'capacity_kg':'provider-confirmed vehicle capacity','dropoff_locations':'complete ordered drop-off stops'}
    actions=[f'Add {labels.get(field,field.replace("_"," "))}.' for field in result['missing']]
    if result['status']=='NEEDS_REVIEW':
        if not quote['full_cost']: actions.append('Confirm the total is the full payable MYR amount.')
        if quote['tax_status']!='included': actions.append('Confirm tax is included in the payable total.')
        if quote['surcharge_status']!='included': actions.append('Confirm surcharges are included in the payable total.')
        if quote['restrictions'] and quote['restrictions'].lower()!='none': actions.append('Review provider restrictions against the order.')
    if result['status'] in ('EXPIRED','INELIGIBLE'): actions.append(result['reason'])
    return actions
