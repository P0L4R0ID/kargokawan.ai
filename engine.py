"""KargoKawan proof-of-concept optimisation core.
All costs/ETAs/carrier capacities are synthetic demonstration assumptions.
No live couriers are connected.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
import math
import pandas as pd
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import lil_matrix

CITIES = {
    "Kuala Lumpur": "peninsular", "George Town": "peninsular", "Johor Bahru": "peninsular",
    "Ipoh": "peninsular", "Melaka": "peninsular", "Kuantan": "peninsular",
    "Kota Kinabalu": "sabah", "Sandakan": "sabah", "Tawau": "sabah",
    "Kuching": "sarawak", "Miri": "sarawak", "Sibu": "sarawak"
}

@dataclass
class Plan:
    kind: str
    provider: str
    ids: tuple
    cost: float
    eta_days: int
    note: str


def lane(o, d):
    if o == d: return 'local'
    a, b = CITIES[o], CITIES[d]
    if a == b and a != 'peninsular': return 'regional'
    if a == 'peninsular' and b == 'peninsular': return 'peninsular'
    if a != 'peninsular' and b != 'peninsular': return 'east_east'
    return 'cross_sea'

# Fictional cost curves, not shipping quotes.
RATES = {
    'Economy': {'local':(8,2,1),'regional':(13,3,2),'peninsular':(15,3.8,3),'east_east':(22,6,5),'cross_sea':(32,9,7)},
    'Express': {'local':(14,3.5,1),'regional':(20,4.5,1),'peninsular':(25,6,2),'east_east':(38,9,3),'cross_sea':(55,13,3)},
}


def validate(df):
    needed = ['order_id','origin','destination','weight_kg','length_cm','width_cm','height_cm','deadline_days']
    missing = [x for x in needed if x not in df]
    if missing: raise ValueError('Missing columns: ' + ', '.join(missing))
    if df.empty: raise ValueError('Please supply at least one order.')
    if len(df) > 20: raise ValueError('Demo supports up to 20 orders to keep group optimisation fast.')
    if df.order_id.astype(str).duplicated().any(): raise ValueError('Order IDs must be unique.')
    for field in ('origin','destination'):
        bad = sorted(set(df[field].dropna().astype(str)) - set(CITIES))
        if bad: raise ValueError(f'Unsupported {field}: {", ".join(bad)}')
    for col in ('weight_kg','length_cm','width_cm','height_cm','deadline_days'):
        if pd.to_numeric(df[col], errors='coerce').isna().any() or (pd.to_numeric(df[col]) <= 0).any():
            raise ValueError(f'{col} must contain positive numbers.')
    if (df.weight_kg > 100).any(): raise ValueError('Max order weight is 100kg in this demo.')
    if not np.all(np.equal(df.deadline_days.astype(float)%1,0)):
        raise ValueError('deadline_days must contain whole numbers.')
    return df.copy().reset_index(drop=True)


def candidates(df, disabled=None):
    disabled=set(disabled or [])
    plans=[]
    records = df.to_dict('records')
    for r in records:
        l=lane(r['origin'],r['destination'])
        billed=max(float(r['weight_kg']),float(r['length_cm'])*float(r['width_cm'])*float(r['height_cm'])/5000)
        if billed <= 30:
            for method in ['Economy','Express']:
                provider = f'Demo {method} Courier'
                base,per_kg,eta=RATES[method][l]
                if provider not in disabled and eta<=int(r['deadline_days']):
                    plans.append(Plan('Individual parcel',provider,(str(r['order_id']),),round(base+per_kg*billed,2),eta, f'{l}: chargeable {billed:.1f} kg'))
        # Synthetic freight option for bulky items; no actual carrier integration.
        if float(r['weight_kg'])<=100 and 'Demo Freight' not in disabled:
            eta=2 if l=='local' else 4 if l in ('regional','peninsular') else 8
            if eta<=int(r['deadline_days']):
                plans.append(Plan('Individual freight','Demo Freight',(str(r['order_id']),),round((80 if l=='cross_sea' else 50)+float(r['weight_kg'])*(8 if l=='cross_sea' else 6),2),eta,'Fictional freight quotation'))
    # Group orders only when matching origin AND matching delivery city.
    # The proposed provider is assumed to have a legitimate consolidation network.
    for (origin,dest), group in df.groupby(['origin','destination']):
        if len(group) < 2: continue
        l=lane(origin,dest)
        vals=group.to_dict('records')
        for k in range(2,min(5,len(vals))+1):
            for subset in combinations(vals,k):
                ids=tuple(str(x['order_id']) for x in subset)
                kg=sum(float(x['weight_kg']) for x in subset)
                if kg>100: continue
                if l=='local':
                    provider='Demo Multi-stop Van'
                    eta=1
                    cost=round(13+5*k+0.8*kg,2)
                    kind='Multi-stop vehicle'
                    note='Same-city route; assumed separate last-mile stops'
                else:
                    provider='Demo Consolidated Freight'
                    eta=5 if l in ('regional','peninsular') else 8
                    if l=='cross_sea': cost=round(70+5.0*kg+9*k,2)
                    elif l=='east_east': cost=round(55+4.2*kg+8*k,2)
                    else: cost=round(35+2.8*kg+7*k,2)
                    kind='Consolidated freight'
                    note='Assumed compatible freight network incl. handling and final distribution'
                if provider not in disabled and all(eta<=int(x['deadline_days']) for x in subset):
                    plans.append(Plan(kind,provider,ids,cost,eta,note))
    return plans


def solve(df, disabled=None):
    df=validate(df)
    options=candidates(df,disabled)
    ids=df.order_id.astype(str).tolist()
    if not options: raise ValueError('No eligible shipping options exist under these restrictions.')
    m=len(options); n=len(ids)
    mat=lil_matrix((n,m),dtype=float)
    lookup={key:i for i,key in enumerate(ids)}
    for j,option in enumerate(options):
        for key in option.ids: mat[lookup[key],j]=1
    res=milp(np.array([x.cost for x in options]),integrality=np.ones(m),bounds=Bounds(np.zeros(m),np.ones(m)),
             constraints=LinearConstraint(mat.tocsr(),np.ones(n),np.ones(n)),options={'time_limit':8,'mip_rel_gap':0.01})
    if res.x is None: raise ValueError('No feasible complete plan. Check deadlines, weight limits, and disabled carriers.')
    selected=[options[i] for i,v in enumerate(res.x) if v>0.5]
    if sorted(k for p in selected for k in p.ids)!=sorted(ids): raise RuntimeError('Optimisation returned an incomplete plan.')
    # Independent shipping baseline: cheapest eligible SINGLE-ORDER method for each order.
    baseline=[]
    for id_ in ids:
        matches=[p for p in options if p.ids==(id_,)]
        if not matches: baseline=None; break
        baseline.append(min(matches,key=lambda p:p.cost))
    base_cost=round(sum(p.cost for p in baseline),2) if baseline is not None else None
    total=round(sum(p.cost for p in selected),2)
    return {'selected':selected,'baseline':baseline,'baseline_cost':base_cost,'total':total,
            'savings':round(base_cost-total,2) if base_cost is not None else None,
            'candidate_count':len(options),'status':str(res.message)}


def to_table(plans):
    return pd.DataFrame([{'Strategy':p.kind,'Provider':p.provider,'Orders':', '.join(p.ids),
                          'Cost (RM)':p.cost,'ETA (days)':p.eta_days,'Assumptions':p.note} for p in plans])


def sample_orders():
    rows=[
    ('KK001','Kuala Lumpur','Kota Kinabalu',4,34,25,20,10),
    ('KK002','Kuala Lumpur','Kota Kinabalu',6,36,28,20,10),
    ('KK003','Kuala Lumpur','Kota Kinabalu',5,36,26,20,10),
    ('PG001','Kuala Lumpur','George Town',4,30,25,20,7),
    ('PG002','Kuala Lumpur','George Town',3,32,25,20,7),
    ('PG003','Kuala Lumpur','George Town',6,30,25,24,7),
    ('JB001','Kuala Lumpur','Johor Bahru',3,30,20,20,5),
    ('JB002','Kuala Lumpur','Johor Bahru',5,30,25,20,5),
    ('KL001','Kuala Lumpur','Kuala Lumpur',2,25,20,15,2),
    ('KL002','Kuala Lumpur','Kuala Lumpur',3,28,25,16,2),
    ('KL003','Kuala Lumpur','Kuala Lumpur',4,30,25,16,2),
    ('KCH001','Kuala Lumpur','Kuching',4,35,24,20,9),
    ('KCH002','Kuala Lumpur','Kuching',5,32,26,20,9),
    ('SDK001','Kota Kinabalu','Sandakan',3,28,24,20,5),
    ('SDK002','Kota Kinabalu','Sandakan',5,30,25,21,5),
    ]
    return pd.DataFrame(rows,columns=['order_id','origin','destination','weight_kg','length_cm','width_cm','height_cm','deadline_days'])


def agent_run(df,disabled=None):
    """Stateful policy agent: checks tools and autonomously chooses lowest-cost viable plan."""
    steps=[]
    steps.append('Triggered: new orders or updated shipping constraints received.')
    valid=validate(df)
    steps.append(f'Validation tool: checked {len(valid)} orders, cities, dimensions and deadlines.')
    outcome=solve(valid,disabled)
    steps.append(f'Candidate generation tool: evaluated {outcome["candidate_count"]} eligible shipping strategies.')
    steps.append(f'Optimisation tool: selected {len(outcome["selected"])} shipment groups covering every order exactly once.')
    if outcome['savings'] is not None:
        steps.append(f'Cost check: standalone RM{outcome["baseline_cost"]:,.2f}; plan RM{outcome["total"]:,.2f}; difference RM{outcome["savings"]:,.2f}.')
    steps.append('Action: prepared proposed shipping manifest for user review. No booking/payment executed.')
    return outcome, steps
