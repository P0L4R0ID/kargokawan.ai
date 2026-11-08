"""User-imported quotations. Upload provenance is a user claim, not carrier authentication."""
import csv
import io
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from itertools import combinations
import pandas as pd

FIELDS = ('quote_id provider service currency source_reference retrieved_at valid_until origin_postcode destination_postcode origin_city destination_city origin_state destination_state physical_weight_kg volumetric_weight_kg max_weight_kg max_length_cm max_width_cm max_height_cm eligible restrictions transport_method total_myr tax_myr surcharge_myr handling_myr last_mile_myr transit_days transit_guaranteed shipment_ids conditions').split()
MONEY = ('total_myr','tax_myr','surcharge_myr','handling_myr','last_mile_myr')
NUMBERS = ('physical_weight_kg','volumetric_weight_kg','max_weight_kg','max_length_cm','max_width_cm','max_height_cm')


def template():
    out=io.StringIO(); csv.DictWriter(out, fieldnames=FIELDS).writeheader(); return out.getvalue()


def import_quotes(data):
    if isinstance(data, bytes): data=data.decode('utf-8-sig')
    reader=csv.DictReader(io.StringIO(data))
    if not reader.fieldnames or set(FIELDS)-set(reader.fieldnames): raise ValueError('Missing quotation columns: '+', '.join(sorted(set(FIELDS)-set(reader.fieldnames or []))))
    if len(reader.fieldnames)!=len(set(reader.fieldnames)): raise ValueError('Duplicate quotation columns.')
    rows=[]; seen=set(); now=datetime.now(timezone.utc)
    for raw in reader:
        if None in raw or any(v is None for v in raw.values()): raise ValueError('Malformed quotation row.')
        q={k:v.strip() for k,v in raw.items()}
        if any(not q[k] for k in ('quote_id','provider','service','source_reference','origin_city','destination_city','origin_state','destination_state','transport_method','shipment_ids','conditions')): raise ValueError('Missing quote identity or provenance.')
        if q['quote_id'] in seen: raise ValueError('Duplicate quote ID.')
        seen.add(q['quote_id'])
        for k in ('origin_postcode','destination_postcode'):
            if not re.fullmatch(r'\d{5}',q[k]): raise ValueError('Malaysian postcodes must have five digits.')
        if q['currency'] != 'MYR': raise ValueError('Only MYR quotations are supported.')
        for k in MONEY+NUMBERS:
            try: q[k]=Decimal(q[k])
            except InvalidOperation: raise ValueError('Invalid amount or dimension.')
            if not q[k].is_finite() or q[k]<0: raise ValueError('Invalid amount or dimension.')
        if q['total_myr']<=0 or any(q[k]<=0 for k in ('physical_weight_kg','max_weight_kg','max_length_cm','max_width_cm','max_height_cm')): raise ValueError('Quote weights, limits and total must be positive.')
        if any(q[k].as_tuple().exponent < -2 for k in MONEY): raise ValueError('MYR amounts need at most two decimal places.')
        for k in ('retrieved_at','valid_until'):
            try: q[k]=datetime.fromisoformat(q[k].replace('Z','+00:00'))
            except ValueError: raise ValueError('Invalid quotation timestamp.')
            if q[k].tzinfo is None: raise ValueError('Quotation timestamps need time zones.')
        if q['valid_until']<=now or q['valid_until']<=q['retrieved_at']: raise ValueError('Expired quotation.')
        try: q['transit_days']=int(q['transit_days'])
        except ValueError: raise ValueError('Invalid transit time.')
        if q['transit_days']<=0: raise ValueError('Invalid transit time.')
        for k in ('eligible','transit_guaranteed'):
            if q[k].lower() not in ('true','false'): raise ValueError('Invalid boolean.')
            q[k]=q[k].lower()=='true'
        ids=[x.strip() for x in q['shipment_ids'].split(';')]
        if not ids or any(not x for x in ids) or len(ids)!=len(set(ids)): raise ValueError('Invalid shipment IDs.')
        q['shipment_ids']=tuple(ids)
        q['source_type']='imported'
        rows.append(q)
    if not rows: raise ValueError('No quotations supplied.')
    return rows


def optimise_imported(orders, quotes):
    from scipy.optimize import milp, Bounds, LinearConstraint
    import numpy as np
    from scipy.sparse import lil_matrix
    required={'order_id','origin','destination','origin_postcode','destination_postcode','weight_kg','length_cm','width_cm','height_cm','deadline_days'}
    if required-set(orders): raise ValueError('Orders need routes, postcodes, dimensions and deadlines.')
    orders=validate_postcodes(orders)
    if orders.empty or orders.order_id.duplicated().any(): raise ValueError('Orders must be nonempty with unique IDs.')
    indexed={str(r['order_id']):r for r in orders.to_dict('records')}
    eligible=[]; now=datetime.now(timezone.utc)
    for q in quotes:
        ids=q['shipment_ids']
        if q['source_type']!='imported' or not q['eligible'] or q['valid_until']<=now or any(x not in indexed for x in ids): continue
        if q['physical_weight_kg'] < sum(Decimal(str(indexed[x]['weight_kg'])) for x in ids): continue
        if any(str(indexed[x]['origin_postcode'])!=q['origin_postcode'] or str(indexed[x]['destination_postcode'])!=q['destination_postcode'] or indexed[x]['origin']!=q['origin_city'] or indexed[x]['destination']!=q['destination_city'] or int(indexed[x]['deadline_days'])<q['transit_days'] or Decimal(str(indexed[x]['weight_kg']))>q['max_weight_kg'] or any(Decimal(str(indexed[x][d]))>q['max_'+d] for d in ('length_cm','width_cm','height_cm')) for x in ids): continue
        if len(ids)>1 and (len({indexed[x]['origin_postcode'] for x in ids})!=1 or len({indexed[x]['destination_postcode'] for x in ids})!=1): continue
        eligible.append(q)
    ids=list(indexed)
    if any(not any(x in q['shipment_ids'] for q in eligible) for x in ids): raise ValueError('NOT QUOTED / UNKNOWN: no complete eligible quote cover.')
    mat=lil_matrix((len(ids),len(eligible)))
    for j,q in enumerate(eligible):
        for x in q['shipment_ids']: mat[ids.index(x),j]=1
    result=milp(np.array([float(q['total_myr']) for q in eligible]),integrality=np.ones(len(eligible)),bounds=Bounds(0,1),constraints=LinearConstraint(mat.tocsr(),1,1))
    if result.x is None: raise ValueError('NOT QUOTED / UNKNOWN: no complete eligible quote cover.')
    selected=[q for q,v in zip(eligible,result.x) if v>0.5]
    baseline=[]
    for x in ids:
        singles=[q for q in eligible if q['shipment_ids']==(x,)]
        if not singles: baseline=None; break
        baseline.append(min(singles,key=lambda q:q['total_myr']))
    total=sum((q['total_myr'] for q in selected),Decimal(0))
    base=sum((q['total_myr'] for q in baseline),Decimal(0)) if baseline else None
    return {'mode':'USER-SUPPLIED IMPORTED QUOTES — not independently authenticated','selected':selected,'total_myr':total,'baseline_myr':base,'difference_myr':base-total if base is not None else None,'eligible_quote_count':len(eligible)}


def validate_postcodes(orders):
    if {'origin_postcode','destination_postcode'}-set(orders):
        raise ValueError('Enter origin and destination postcodes for every imported-quote order.')
    result=orders.copy()
    for field in ('origin_postcode','destination_postcode'):
        result[field]=result[field].astype(str).str.strip()
        if not result[field].str.fullmatch(r'\d{5}').all():
            raise ValueError(f'{field} must be a five-digit Malaysian postcode.')
    return result


def quote_fingerprint(orders, quotes, unavailable=()):
    import hashlib
    payload=orders.to_csv(index=False)+repr(sorted(unavailable))+repr(sorted((q['quote_id'],repr(sorted(q.items()))) for q in quotes))
    return hashlib.sha256(payload.encode()).hexdigest()


def preview_imported(orders, quotes, unavailable=()):
    orders=validate_postcodes(orders)
    filtered=[q for q in quotes if q['provider'] not in unavailable]
    plan=optimise_imported(orders,filtered)
    return {'fingerprint':quote_fingerprint(orders,quotes,unavailable),'plan':plan}


def approve_imported(preview, orders, quotes, unavailable=()):
    if preview['fingerprint']!=quote_fingerprint(validate_postcodes(orders),quotes,unavailable):
        raise ValueError('Inputs changed; generate a fresh imported quote preview.')
    current=preview_imported(orders,quotes,unavailable)
    return current['plan']


def imported_manifest(plan):
    return pd.DataFrame([{'Data status':'USER-SUPPLIED QUOTATION — PROPOSAL ONLY / NOT A BOOKING',
        'Quote ID':q['quote_id'],'Provider':q['provider'],'Service':q['service'],
        'Orders':';'.join(q['shipment_ids']),'Quoted total (MYR)':str(q['total_myr']),
        'Source reference':q['source_reference'],'Retrieved at':q['retrieved_at'].isoformat(),
        'Valid until':q['valid_until'].isoformat()} for q in plan['selected']])
