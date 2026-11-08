from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from hybrid_quotes import normalize
from delivery_operations import JobStore,checklist

def order(): return {'order_id':'A','recipient':'Test Recipient','origin_postcode':'50000','destination_postcode':'10000','weight_kg':1,'length_cm':10,'width_cm':10,'height_cm':10,'deadline_days':2}
def quote():
 now=datetime.now(timezone.utc)
 return normalize({'quote_id':'TEST-Q','source_class':'USER_IMPORTED_UNVERIFIED','provider':'EasyParcel Malaysia','service':'Test','transport_method':'parcel_courier','origin_postcode':'50000','destination_postcode':'10000','pickup_location':'Test pickup','dropoff_locations':'','shipment_ids':'A','physical_weight_kg':'1','length_cm':'20','width_cm':'20','height_cm':'20','capacity_kg':'2','displayed_cost_myr':'20.00','full_cost':'true','tax_status':'included','surcharge_status':'included','source_reference':'SYNTHETIC TEST FIXTURE','collected_at':now.isoformat(),'valid_until':(now+timedelta(days=1)).isoformat(),'transit_days':'1','restrictions':'none'})
def test_intake_lifecycle_persistence_and_evidence(tmp_path):
 store=JobStore(tmp_path/'jobs.sqlite');q=quote();job=store.create([order()]);assert store.get(job)['state']=='DRAFT'
 assert JobStore(tmp_path/'jobs.sqlite').get(job)['events'][0]['action']=='CREATED'
 store.propose(job,[order()],[q]);assert store.get(job)['state']=='READY_FOR_REVIEW'
 store.approve(job,[order()],[q]);assert store.get(job)['state']=='APPROVED'
 assert 'NOT A BOOKING' in store.manifest(job)['Status'][0]
 store.transition(job,'PREPARED');store.transition(job,'AWAITING_BOOKING')
 with pytest.raises(ValueError):store.record_booking(job,'','','')
 store.record_booking(job,'PROVIDER-TEST','TRACK-TEST','External confirmation document')
 with pytest.raises(ValueError):store.set_inputs(job,[order()],[quote()])
 with pytest.raises(ValueError):store.transition(job,'IN_TRANSIT')
 store.transition(job,'IN_TRANSIT',evidence='Provider tracking page')
 store.transition(job,'DELIVERED',evidence='Proof of delivery')
 assert store.get(job)['state']=='DELIVERED'
def test_missing_intake_and_stale_approval(tmp_path):
 store=JobStore(tmp_path/'jobs.sqlite');bad=order();bad['recipient']='';bad['destination_postcode']='123'
 assert len(checklist([bad]))>=2
 job=store.create([bad]);assert store.get(job)['state']=='NEEDS_INFORMATION'
 with pytest.raises(ValueError,match='Missing'):store.propose(job,[bad],[quote()])
 store.set_inputs(job,[order()],[quote()]);store.propose(job,[order()],[quote()])
 changed=order();changed['deadline_days']=3
 with pytest.raises(ValueError,match='fresh'):store.approve(job,[changed],[quote()])
 store.set_inputs(job,[changed],[quote()]);assert store.get(job)['proposal'] is None
def test_no_external_booking_adapter():
 from carrier_adapters import FocusedProviderAdapter
 assert FocusedProviderAdapter('EasyParcel Malaysia').fetch_rates({})['status']=='NOT_CONNECTED'
