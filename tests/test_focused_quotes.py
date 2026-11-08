from datetime import datetime,timedelta,timezone
from decimal import Decimal
import pandas as pd
import pytest
from focused_quotes import evaluate,preview,approve,import_provider,template
from hybrid_quotes import normalize
from carrier_adapters import FocusedProviderAdapter

NOW=datetime.now(timezone.utc)
ORDERS=pd.DataFrame([{'order_id':'A','origin_postcode':'50000','destination_postcode':'10000','weight_kg':1,'deadline_days':2},{'order_id':'B','origin_postcode':'50000','destination_postcode':'10001','weight_kg':1,'deadline_days':2}])
def q(provider,ids,method,cost):
    stops=[{'shipment_id':x,'postcode':'10000' if x=='A' else '10001','sequence':i+1} for i,x in enumerate(ids)]
    import json
    return normalize({'quote_id':provider+ids[0],'source_class':'USER_IMPORTED_UNVERIFIED','provider':provider,'service':'Test service','transport_method':method,'origin_postcode':'50000','destination_postcode':'10000' if ids[0]=='A' else '10001','pickup_location':'Synthetic pickup','dropoff_locations':json.dumps(stops) if method=='multi_stop_vehicle' else '', 'shipment_ids':';'.join(ids),'physical_weight_kg':str(len(ids)),'length_cm':'10','width_cm':'10','height_cm':'10','capacity_kg':'10','displayed_cost_myr':cost,'full_cost':'true','tax_status':'included','surcharge_status':'included','source_reference':'SYNTHETIC TEST DOCUMENT','collected_at':NOW.isoformat(),'valid_until':(NOW+timedelta(days=1)).isoformat(),'transit_days':'1','restrictions':'none'})
def quotes(): return [q('EasyParcel Malaysia',['A'],'parcel_courier','20.00'),q('EasyParcel Malaysia',['B'],'parcel_courier','20.00')],[q('Lalamove Malaysia',['A','B'],'multi_stop_vehicle','30.00')]
def test_comparable_and_approval_staleness():
 c,v=quotes(); result=evaluate(ORDERS,c,v)
 assert result['status']=='COMPARABLE' and result['difference_myr']==Decimal('10.00')
 p=preview(ORDERS,c,v);assert approve(p,ORDERS,c,v)['status']=='COMPARABLE'
 changed=ORDERS.copy();changed.loc[0,'deadline_days']=0
 with pytest.raises(ValueError,match='fresh'): approve(p,changed,c,v)
def test_partial_expired_capacity_and_route_excluded():
 c,v=quotes();c[0]['tax_status']='UNKNOWN';assert evaluate(ORDERS,c,v)['status']=='NOT READY'
 c,v=quotes();v[0]['capacity_kg']=Decimal('1');assert evaluate(ORDERS,c,v)['status']=='NOT READY'
 c,v=quotes();v[0]['dropoff_locations'][1]['postcode']='90000';assert evaluate(ORDERS,c,v)['status']=='NOT READY'
 c,v=quotes();v[0]['valid_until']=NOW-timedelta(days=1);assert evaluate(ORDERS,c,v)['status']=='NOT READY'
 c,v=quotes();v[0]['source_class']='PUBLIC_REFERENCE';assert evaluate(ORDERS,c,v)['status']=='NOT READY'
def test_connections_and_import_restrictions():
 for p in ('EasyParcel Malaysia','Lalamove Malaysia','Pos Malaysia'):
  assert FocusedProviderAdapter(p).fetch_rates({})['status']=='NOT_CONNECTED'
 assert template('EasyParcel Malaysia').startswith('quote_id,')
 with pytest.raises(ValueError): import_provider('EasyParcel Malaysia',template('EasyParcel Malaysia'))
