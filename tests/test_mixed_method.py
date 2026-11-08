from datetime import datetime,timedelta,timezone
from decimal import Decimal
import pandas as pd
import pytest
from hybrid_quotes import normalize
from mixed_method import optimize,preview,approve

NOW=datetime.now(timezone.utc)
ORDERS=pd.DataFrame([{'order_id':x,'origin_postcode':'50000','destination_postcode':p,'weight_kg':1,'length_cm':10,'width_cm':10,'height_cm':10,'deadline_days':2} for x,p in [('A','10000'),('B','10001'),('C','10002')]])
def quote(ids,cost,vehicle=False):
 import json
 stops=[{'shipment_id':x,'postcode':{'A':'10000','B':'10001','C':'10002'}[x],'sequence':i+1} for i,x in enumerate(ids)]
 return normalize({'quote_id':('V' if vehicle else 'C')+''.join(ids),'source_class':'USER_IMPORTED_UNVERIFIED','provider':'Lalamove Malaysia' if vehicle else 'EasyParcel Malaysia','service':'Complete test quote','transport_method':'multi_stop_vehicle' if vehicle else 'parcel_courier','origin_postcode':'50000','destination_postcode':stops[0]['postcode'],'pickup_location':'Test pickup','dropoff_locations':json.dumps(stops) if vehicle else '', 'shipment_ids':';'.join(ids),'physical_weight_kg':str(len(ids)),'length_cm':'20','width_cm':'20','height_cm':'20','capacity_kg':'10','displayed_cost_myr':str(cost),'full_cost':'true','tax_status':'included','surcharge_status':'included','source_reference':'SYNTHETIC TEST EVIDENCE','collected_at':NOW.isoformat(),'valid_until':(NOW+timedelta(days=1)).isoformat(),'transit_days':'1','restrictions':'none'})
def batch():return [quote([x],20) for x in 'ABC']+[quote(['A','B'],25,True)]
def test_mixed_subset_and_exact_cover():
 result=optimize(ORDERS,batch())
 assert result['status']=='READY' and result['total_myr']==45 and result['baseline_myr']==60
 assert {q['quote_id'] for q in result['selected']}=={'VAB','CC'}
 assert sorted(x for q in result['selected'] for x in q['shipment_ids'])==['A','B','C']
def test_all_courier_and_missing_baseline():
 qs=batch();qs[-1]['displayed_cost_myr']=Decimal('50')
 assert optimize(ORDERS,qs)['total_myr']==60
 qs=batch();qs.pop(0)
 result=optimize(ORDERS,qs)
 assert result['status']=='READY' and result['baseline_myr'] is None
 qs=[quote(['A','B'],25,True)]
 assert optimize(ORDERS,qs)['status']=='NOT READY'
def test_ineligible_route_capacity_expiry_and_sources():
 for field,value in [('capacity_kg',Decimal(1)),('valid_until',NOW-timedelta(days=1)),('source_class','PUBLIC_REFERENCE'),('source_class','SYNTHETIC')]:
  qs=batch();qs[-1][field]=value
  assert optimize(ORDERS,qs)['total_myr']==60
 qs=batch();qs[-1]['dropoff_locations'][1]['postcode']='99999'
 assert optimize(ORDERS,qs)['total_myr']==60
 qs=batch();qs[-1]['full_cost']=False
 assert optimize(ORDERS,qs)['total_myr']==60
def test_stale_preview_and_availability():
 qs=batch();proposal=preview(ORDERS,qs)
 assert approve(proposal,ORDERS,qs)['total_myr']==45
 with pytest.raises(ValueError,match='fresh'):approve(proposal,ORDERS,qs,['Lalamove Malaysia'])
 changed=ORDERS.copy();changed.loc[0,'weight_kg']=2
 with pytest.raises(ValueError,match='fresh'):approve(proposal,changed,qs)
 assert optimize(ORDERS,qs,['Lalamove Malaysia'])['total_myr']==60
