from pathlib import Path
import pytest
from conversation_intake import extract,followups,validate_draft
from sample_intake import load_sample_intake
from delivery_operations import JobStore

def test_partial_request_and_no_invention():
 result=extract('I have 3 orders, budget RM80.\nOrder A: from Kuala Lumpur to Kuching, 2 kg, within 7 days')
 row=result['orders'].iloc[0]
 assert result['requested_quantity']==3 and result['budget_myr']=='80'
 assert row['origin']=='Kuala Lumpur' and row['destination']=='Kuching'
 assert row['recipient']=='' and row['destination_postcode']==''
 assert result['notes'] and any('recipient' in x for x in followups(result['orders']))
def test_correction_and_safe_job_creation(tmp_path):
 text='Order A: from Kuala Lumpur 50000 to Kuching 93000, 2 kg, 30x20x10 cm, within 7 days'
 draft=extract(text)['orders']
 with pytest.raises(ValueError):validate_draft(draft)
 draft.loc[0,'recipient']='FICTIONAL CUSTOMER'
 valid=validate_draft(draft)
 store=JobStore(tmp_path/'jobs.sqlite');job=store.create(valid)
 assert store.get(job)['state']=='DRAFT' and store.get(job)['booking'] is None
def test_csv_continuation_and_bad_postcode():
 path=Path(__file__).resolve().parents[1]/'data/samples/malaysia_sme_incomplete_orders.csv'
 draft=load_sample_intake(path.read_text())
 assert len(followups(draft))>=3
 draft.loc[1,'recipient']='FICTIONAL CUSTOMER'
 draft.loc[2,'destination_postcode']='80000'
 draft.loc[3,'origin_postcode']='50000'
 assert len(validate_draft(draft))==5
 draft.loc[0,'origin_postcode']='5000'
 with pytest.raises(ValueError):validate_draft(draft)

def test_conversational_ui_draft_edit_flow():
 from streamlit.testing.v1 import AppTest
 app=AppTest.from_file('../app.py',default_timeout=20).run()
 area=next(x for x in app.text_area if x.label=='Describe your logistics goal')
 area.set_value('Order A: from Kuala Lumpur 50000 to Kuching 93000, 2 kg, 30x20x10 cm, within 7 days').run()
 next(b for b in app.button if b.label=='Extract explicit order details').click().run()
 assert not app.exception
 assert len(app.session_state['ops_sample'])==1
 assert app.session_state['ops_sample'].iloc[0]['recipient']==''
 assert any('recipient' in str(x.value).lower() for x in app.get('markdown'))
