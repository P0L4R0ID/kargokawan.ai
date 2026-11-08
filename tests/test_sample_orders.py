from pathlib import Path
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from sample_intake import load_sample_intake,validate_complete
from delivery_operations import checklist
from dashboard import normalize
from quotes import validate_postcodes

ROOT=Path(__file__).resolve().parents[1]/'data/samples'
def test_complete_sample_matches_both_contracts():
 data=(ROOT/'malaysia_sme_5_orders.csv').read_text()
 orders=validate_complete(data)
 assert len(orders)==5 and orders.order_id.is_unique
 assert checklist(orders.to_dict('records'))==[]
 assert len(normalize(orders))==5
 assert validate_postcodes(orders).origin_postcode.iloc[0]=='50000'
 assert {'Kota Kinabalu','Kuching','George Town','Johor Bahru'}<=set(orders.destination)
def test_incomplete_sample_generates_actions():
 data=(ROOT/'malaysia_sme_incomplete_orders.csv').read_text()
 orders=load_sample_intake(data)
 tasks=checklist(orders.to_dict('records'))
 assert tasks==['Order 2: supply recipient','Order 3: supply destination_postcode','Order 4: supply origin_postcode']
def test_operations_upload_ui_with_injected_file():
 data=(ROOT/'malaysia_sme_5_orders.csv').read_bytes()
 class Upload:
  def getvalue(self): return data
 original=__import__('streamlit').file_uploader
 def uploader(label,*args,**kwargs):
  return Upload() if label=='Import delivery operations CSV' else None
 with patch('streamlit.file_uploader',side_effect=uploader):
  app=AppTest.from_file('../app.py',default_timeout=20).run()
  assert not app.exception
  assert len(app.session_state['ops_sample'])==5
  assert app.session_state['ops_sample'].iloc[0]['recipient']=='SYNTHETIC CUSTOMER A'
