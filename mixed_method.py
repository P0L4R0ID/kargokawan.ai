"""Deterministic exact-cover selection from complete, explicit quotations."""
from decimal import Decimal
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import lil_matrix
import numpy as np
from focused_quotes import _orders, fingerprint
from hybrid_quotes import review

MAX_ORDERS=20
MAX_QUOTES=500

def _eligible(quote,orders,unavailable,demo=False):
    if quote['provider'] in unavailable or quote['source_class'] not in (('SYNTHETIC',) if demo else ('USER_IMPORTED_UNVERIFIED','LIVE_AUTHENTICATED')):
        return False,'Unavailable provider or non-executable provenance.'
    result=review(quote,orders)
    if result['status']!='ELIGIBLE': return False,result['reason']
    by_id={str(x['order_id']):x for x in orders}
    if quote['transport_method'] not in ('parcel_courier','multi_stop_vehicle'): return False,'Unsupported transport method.'
    if quote['transport_method']=='parcel_courier' and len(quote['shipment_ids'])!=1: return False,'Courier quote must cover one shipment.'
    if quote['transport_method']=='multi_stop_vehicle' and len(quote['shipment_ids'])<2: return False,'Vehicle route needs multiple explicit stops.'
    if any(Decimal(str(by_id[x][dim]))>quote[dim] for x in quote['shipment_ids'] for dim in ('length_cm','width_cm','height_cm')): return False,'Shipment dimensions exceed quoted limits.'
    if quote['physical_weight_kg']<sum(Decimal(str(by_id[x]['weight_kg'])) for x in quote['shipment_ids']): return False,'Quoted physical weight is below shipment total.'
    return True,'Eligible full-cost quotation.'

def optimize(orders,quotes,unavailable=(),demo=False):
    data=_orders(orders); ids=[str(x['order_id']) for x in data]
    if len(ids)>MAX_ORDERS or len(quotes)>MAX_QUOTES: raise ValueError('Operational limit: at most 20 orders and 500 quotations.')
    reviewed=[]; usable=[]
    for q in quotes:
        valid,reason=_eligible(q,data,unavailable,demo)
        reviewed.append({'quote_id':q['quote_id'],'provider':q['provider'],'status':'ELIGIBLE' if valid else 'EXCLUDED','reason':reason})
        if valid: usable.append(q)
    baseline=[]
    for oid in ids:
        choices=[q for q in usable if q['transport_method']=='parcel_courier' and q['shipment_ids']==(oid,)]
        if not choices: baseline=None;break
        baseline.append(min(choices,key=lambda q:(q['displayed_cost_myr'],q['quote_id'])))
    baseline_cost=sum((q['displayed_cost_myr'] for q in baseline),Decimal(0)) if baseline is not None else None
    if not usable or any(not any(x in q['shipment_ids'] for q in usable) for x in ids):
        return {'status':'NOT READY','reason':'No complete eligible quote cover for every order.','baseline_myr':baseline_cost,'selected':[],'total_myr':None,'difference_myr':None,'reviewed':reviewed}
    matrix=lil_matrix((len(ids),len(usable)))
    for j,q in enumerate(usable):
        for oid in q['shipment_ids']: matrix[ids.index(oid),j]=1
    costs=np.array([float(q['displayed_cost_myr']) for q in usable])
    solution=milp(costs,integrality=np.ones(len(usable)),bounds=Bounds(np.zeros(len(usable)),np.ones(len(usable))),constraints=LinearConstraint(matrix.tocsr(),np.ones(len(ids)),np.ones(len(ids))),options={'time_limit':8,'mip_rel_gap':0.0})
    if solution.x is None or solution.status not in (0,1): return {'status':'NOT READY','reason':'Eligible quotes overlap without a complete exact cover.','baseline_myr':baseline_cost,'selected':[],'total_myr':None,'difference_myr':None,'reviewed':reviewed}
    x=np.asarray(solution.x)
    if len(x)!=len(usable) or not np.isfinite(x).all() or np.any(x < -1e-6) or np.any(x > 1+1e-6) or np.any(np.abs(x-np.rint(x))>1e-6) or not np.allclose(matrix.tocsr() @ x,np.ones(len(ids)),atol=1e-6):
        return {'status':'NOT READY','reason':'Solver returned a numerically invalid plan.','baseline_myr':baseline_cost,'selected':[],'total_myr':None,'difference_myr':None,'reviewed':reviewed}
    selected=[q for q,v in zip(usable,x) if v>0.5]
    if sorted(x for q in selected for x in q['shipment_ids'])!=sorted(ids): raise RuntimeError('Incomplete quote cover.')
    total=sum((q['displayed_cost_myr'] for q in selected),Decimal(0))
    decisions=[{'quote_id':q['quote_id'],'provider':q['provider'],'service':q['service'],'method':q['transport_method'],'shipment_ids':q['shipment_ids'],'total_myr':q['displayed_cost_myr'],'tax_status':q['tax_status'],'surcharge_status':q['surcharge_status'],'source_class':q['source_class'],'source_reference':q['source_reference'],'valid_until':q['valid_until'],'reason':'Selected as part of the minimum-cost complete exact cover among eligible full-cost quotes.'} for q in selected]
    return {'status':'READY' if solution.status==0 else 'SOLVER LIMITED','reason':'Proven minimum-cost exact cover.' if solution.status==0 else 'Feasible exact cover; solver limit prevents optimality claim.','selected':selected,'decisions':decisions,'total_myr':total,'baseline_myr':baseline_cost,'difference_myr':baseline_cost-total if baseline_cost is not None else None,'reviewed':reviewed,'claim':'SIMULATED DEMO — NOT REAL CARRIER PRICES' if demo else 'USER_IMPORTED_UNVERIFIED; source labels are not independent authentication'}

def preview(orders,quotes,unavailable=(),demo=False):
    result=optimize(orders,quotes,unavailable,demo)
    if result['status'] not in ('READY','SOLVER LIMITED'): raise ValueError(result['reason'])
    return {'fingerprint':fingerprint(orders,quotes,[])+repr(sorted(unavailable))+repr(demo),'result':result}

def approve(proposal,orders,quotes,unavailable=(),demo=False):
    if proposal['fingerprint']!=fingerprint(orders,quotes,[])+repr(sorted(unavailable))+repr(demo): raise ValueError('Inputs changed; generate a fresh mixed-method preview.')
    result=optimize(orders,quotes,unavailable,demo)
    if result['status'] not in ('READY','SOLVER LIMITED'): raise ValueError(result['reason'])
    return result
