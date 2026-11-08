from datetime import datetime,timedelta,timezone
import pandas as pd
from quote_guidance import request_checklist,request_details,vehicle_candidates,make_draft,revise_draft,collection_progress
from hybrid_quotes import review
from delivery_operations import JobStore
from tests.test_mixed_method import quote as example_quote, ORDERS as example_orders

def test_request_details_exclude_recipients_and_cross_sea_vehicle():
 rows=[{'order_id':'A','recipient':'PRIVATE','origin':'Kuala Lumpur','destination':'George Town','origin_postcode':'50000','destination_postcode':'10000','weight_kg':1,'length_cm':10,'width_cm':10,'height_cm':10,'deadline_days':3},
       {'order_id':'B','recipient':'PRIVATE','origin':'Kuala Lumpur','destination':'Johor Bahru','origin_postcode':'50000','destination_postcode':'80000','weight_kg':1,'length_cm':10,'width_cm':10,'height_cm':10,'deadline_days':3},
       {'order_id':'C','recipient':'PRIVATE','origin':'Kuala Lumpur','destination':'Kuching','origin_postcode':'50000','destination_postcode':'93000','weight_kg':1,'length_cm':10,'width_cm':10,'height_cm':10,'deadline_days':7}]
 assert 'recipient' not in request_details(rows)[0]
 assert len(request_checklist(rows))==3
 candidates=vehicle_candidates(rows)
 assert len(candidates)==1 and candidates[0]['shipment_ids']==['A','B']
 assert candidates[0]['stops'][1]['postcode']=='80000'
def test_draft_correction_missing_tax_and_expiry():
 now=datetime.now(timezone.utc)
 fields={'quote_id':'Q','provider':'EasyParcel Malaysia','service':'Parcel','transport_method':'parcel_courier','origin_postcode':'50000','destination_postcode':'10000','pickup_location':'Test','shipment_ids':'A','physical_weight_kg':'1','length_cm':'20','width_cm':'20','height_cm':'20','capacity_kg':'2','displayed_cost_myr':'20.00','full_cost':'true','tax_status':'UNKNOWN','surcharge_status':'included','source_reference':'TEST EVIDENCE','valid_until':'','transit_days':'1','restrictions':'none'}
 draft=make_draft(fields)
 assert review(draft,example_orders.to_dict('records'))['status']=='INCOMPLETE'
 revised=revise_draft(draft,{'tax_status':'included','valid_until':(now+timedelta(days=1)).isoformat()})
 assert review(revised,example_orders.to_dict('records'))['status']=='ELIGIBLE'
 revised=revise_draft(revised,{'destination_postcode':'99999'})
 assert review(revised,example_orders.to_dict('records'))['status']=='INELIGIBLE'
def test_quote_progress_and_plan_handoff(tmp_path):
 orders=example_orders.copy();orders['recipient']='FICTIONAL'
 quotes=[example_quote([x],20) for x in 'ABC']+[example_quote(['A','B'],25,True)]
 progress=collection_progress(orders,quotes)
 assert progress['plan']['status']=='READY'
 assert progress['plan']['total_myr']==45
 assert progress['courier_by_order']['C']
 store=JobStore(tmp_path/'jobs.sqlite');job=store.create(orders)
 store.propose(job,orders,quotes)
 assert store.get(job)['state']=='READY_FOR_REVIEW'
 assert store.get(job)['booking'] is None
