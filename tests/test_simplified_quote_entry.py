from datetime import date,time,datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from delivery_operations import JobStore
from sample_intake import validate_complete
from quote_guidance import order_facts,malaysia_timestamp,make_draft,missing_quote_actions
from hybrid_quotes import review
import pytest

ROOT=Path(__file__).resolve().parents[1]
def orders(): return validate_complete((ROOT/'data/samples/malaysia_sme_5_orders.csv').read_text())
def test_autofill_order_facts_and_no_provider_limits():
 data=orders();facts=order_facts(data,['SME002'])
 assert facts['origin_postcode']=='50000' and facts['destination_postcode']=='10000'
 assert facts['physical_weight_kg']==3 and facts['max_order_length_cm']==32
 assert 'capacity_kg' not in facts and 'displayed_cost_myr' not in facts
 with pytest.raises(ValueError): order_facts(data,['MISSING'])
def test_vehicle_stops_and_timezone():
 data=orders();facts=order_facts(data,['SME002','SME003'])
 assert [x['sequence'] for x in facts['stops']]==[1,2]
 assert [x['postcode'] for x in facts['stops']]==['10000','80000']
 stamp=malaysia_timestamp(date(2026,11,9),time(14,30))
 assert stamp.isoformat()=='2026-11-09T14:30:00+08:00'
def test_missing_evidence_checklist_and_unverified_source():
 now=datetime.now(timezone.utc)
 fields={'quote_id':'Q','provider':'EasyParcel Malaysia','service':'Parcel','transport_method':'parcel_courier','origin_postcode':'50000','destination_postcode':'10000','pickup_location':'Test pickup','shipment_ids':'SME002','physical_weight_kg':'3','length_cm':'32','width_cm':'24','height_cm':'18','displayed_cost_myr':'20.00','full_cost':'true','tax_status':'UNKNOWN','surcharge_status':'UNKNOWN','valid_until':'','transit_days':'2','restrictions':'none','source_reference':'TEST EVIDENCE'}
 draft=make_draft(fields)
 assert draft['source_class']=='USER_IMPORTED_UNVERIFIED'
 assert any('expiry' in x for x in missing_quote_actions(draft,orders().to_dict('records')))
 assert review(draft,orders().to_dict('records'))['status']=='INCOMPLETE'
 fields['valid_until']=(now+timedelta(days=1)).isoformat()
 fields['tax_status']='included';fields['surcharge_status']='included'
 assert review(make_draft(fields),orders().to_dict('records'))['status']=='ELIGIBLE'
def test_provider_specific_form_fields(tmp_path):
 store=JobStore(tmp_path/'jobs.sqlite');store.create(orders())
 with patch('delivery_operations.JobStore',return_value=store):
  app=AppTest.from_file('../app.py',default_timeout=20).run()
  assert not app.exception
  assert any(x.label=='Select delivery job' for x in app.selectbox)
  assert not any(x.label=='Provider-confirmed vehicle capacity (kg)' for x in app.text_input)
  next(x for x in app.selectbox if x.label=='Choose quotation provider').set_value('Lalamove Malaysia').run()
  assert not app.exception
  assert any(x.label=='Provider-confirmed vehicle capacity (kg)' for x in app.text_input)
  assert any(x.label=='Choose orders covered by the vehicle quote' for x in app.multiselect)
