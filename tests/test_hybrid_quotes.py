from datetime import datetime,timedelta,timezone
from decimal import Decimal
from hybrid_quotes import normalize,review,parse_csv,template
from carrier_adapters import MissingCredentialAdapter

def sample():
 now=datetime.now(timezone.utc)
 return {'quote_id':'Q1','source_class':'SYNTHETIC','provider':'Test vehicle','service':'Dedicated','transport_method':'multi_stop_vehicle','origin_postcode':'50000','destination_postcode':'10000','pickup_location':'Warehouse 50000','dropoff_locations':'[{"shipment_id":"A","postcode":"10000"},{"shipment_id":"B","postcode":"10001"}]','shipment_ids':'A;B','physical_weight_kg':'2','length_cm':'10','width_cm':'10','height_cm':'10','capacity_kg':'10','displayed_cost_myr':'30.00','full_cost':'true','tax_status':'included','surcharge_status':'included','source_reference':'SYNTHETIC TEST','collected_at':now.isoformat(),'valid_until':(now+timedelta(days=1)).isoformat(),'transit_days':'1','restrictions':'none'}
def orders(): return [{'order_id':x,'origin_postcode':'50000','destination_postcode':p,'weight_kg':1,'deadline_days':2} for x,p in [('A','10000'),('B','10001')]]
def test_multistop_coverage_and_provenance():
 raw=sample();q=normalize(raw)
 assert review(q,orders())['status']=='ELIGIBLE'
 raw['source_class']='PUBLIC_REFERENCE';assert review(normalize(raw),orders())['status']=='INCOMPLETE'
 raw=sample();raw['dropoff_locations']='[{"shipment_id":"A","postcode":"10000"}]'
 assert review(normalize(raw),orders())['status']=='INELIGIBLE'
def test_missing_data_expiry_tax_and_capacity():
 raw=sample();raw['tax_status']='';assert review(normalize(raw),orders())['status']=='INCOMPLETE'
 raw=sample();raw['valid_until']='';assert review(normalize(raw),orders())['status']=='INCOMPLETE'
 raw=sample();raw['full_cost']='false';assert review(normalize(raw),orders())['status']=='NEEDS_REVIEW'
 raw=sample();raw['capacity_kg']='1';assert review(normalize(raw),orders())['status']=='INELIGIBLE'
 raw=sample();raw['valid_until']=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat();assert review(normalize(raw),orders())['status']=='EXPIRED'
def test_csv_and_disabled_adapter():
 import csv,io
 row=sample();out=io.StringIO();w=csv.DictWriter(out,fieldnames=template().strip().split(','));w.writeheader();w.writerow(row)
 assert parse_csv(out.getvalue())[0]['displayed_cost_myr']==Decimal('30.00')
 assert MissingCredentialAdapter('Test').fetch_rates({})['status']=='MISSING_CREDENTIALS'
