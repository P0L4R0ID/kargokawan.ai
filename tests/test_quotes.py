import io
from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest
from quotes import import_quotes, optimise_imported


def test_imported_quotes_require_provenance_and_never_invent_groups():
    now = datetime.now(timezone.utc)
    orders = pd.DataFrame([
        {'order_id':'A','origin':'Kuala Lumpur','destination':'George Town','origin_postcode':'50000','destination_postcode':'10000','weight_kg':1,'length_cm':10,'width_cm':10,'height_cm':10,'deadline_days':3},
        {'order_id':'B','origin':'Kuala Lumpur','destination':'George Town','origin_postcode':'50000','destination_postcode':'10000','weight_kg':1,'length_cm':10,'width_cm':10,'height_cm':10,'deadline_days':3}])
    rows=[]
    for oid in ('A','B'):
        rows.append({'quote_id':oid,'provider':'Actual carrier','service':'Parcel','currency':'MYR','source_reference':'user document','retrieved_at':now.isoformat(),'valid_until':(now+timedelta(days=1)).isoformat(),'origin_postcode':'50000','destination_postcode':'10000','origin_city':'Kuala Lumpur','destination_city':'George Town','origin_state':'WP Kuala Lumpur','destination_state':'Pulau Pinang','physical_weight_kg':'1','volumetric_weight_kg':'0.2','max_weight_kg':'2','max_length_cm':'20','max_width_cm':'20','max_height_cm':'20','eligible':'true','restrictions':'none','transport_method':'road','total_myr':'12.50','tax_myr':'0','surcharge_myr':'0','handling_myr':'0','last_mile_myr':'0','transit_days':'2','transit_guaranteed':'false','shipment_ids':oid,'conditions':'standard'})
    quotes=import_quotes(pd.DataFrame(rows).to_csv(index=False))
    result=optimise_imported(orders,quotes)
    assert result['total_myr']==25
    assert len(result['selected'])==2
    assert all(q['source_type']=='imported' for q in result['selected'])
    with pytest.raises(ValueError): import_quotes(pd.DataFrame(rows).drop(columns=['source_reference']).to_csv(index=False))
    rows[0]['valid_until']=(now-timedelta(days=1)).isoformat()
    with pytest.raises(ValueError): import_quotes(pd.DataFrame(rows).to_csv(index=False))


def test_postcode_and_stale_preview():
    from quotes import validate_postcodes, preview_imported, approve_imported, imported_manifest
    now=datetime.now(timezone.utc)
    order=pd.DataFrame([{'order_id':'A','origin':'Kuala Lumpur','destination':'George Town','origin_postcode':'01000','destination_postcode':'10000','weight_kg':1,'length_cm':10,'width_cm':10,'height_cm':10,'deadline_days':3}])
    assert validate_postcodes(order).iloc[0].origin_postcode=='01000'
    bad=order.copy(); bad.loc[0,'origin_postcode']='1000'
    with pytest.raises(ValueError,match='five-digit'): validate_postcodes(bad)
    row={'quote_id':'Q','provider':'Carrier','service':'Parcel','currency':'MYR','source_reference':'document','retrieved_at':now.isoformat(),'valid_until':(now+timedelta(days=1)).isoformat(),'origin_postcode':'01000','destination_postcode':'10000','origin_city':'Kuala Lumpur','destination_city':'George Town','origin_state':'Kedah','destination_state':'Penang','physical_weight_kg':'1','volumetric_weight_kg':'0.2','max_weight_kg':'2','max_length_cm':'20','max_width_cm':'20','max_height_cm':'20','eligible':'true','restrictions':'none','transport_method':'road','total_myr':'10.00','tax_myr':'0','surcharge_myr':'0','handling_myr':'0','last_mile_myr':'0','transit_days':'2','transit_guaranteed':'false','shipment_ids':'A','conditions':'standard'}
    quote=import_quotes(pd.DataFrame([row]).to_csv(index=False))
    preview=preview_imported(order,quote)
    assert approve_imported(preview,order,quote)['total_myr']==10
    assert 'Q' in imported_manifest(preview['plan'])['Quote ID'].tolist()
    changed=order.copy(); changed.loc[0,'deadline_days']=1
    with pytest.raises(ValueError,match='fresh'): approve_imported(preview,changed,quote)
    with pytest.raises(ValueError,match='NOT QUOTED'): preview_imported(changed,quote)
    row['quote_id']='Q2'; row['origin_postcode']='02000'
    with pytest.raises(ValueError,match='NOT QUOTED'): preview_imported(order,import_quotes(pd.DataFrame([row]).to_csv(index=False)))
    row['quote_id']='Q'; row['origin_postcode']='01000'; row['total_myr']='0'
    with pytest.raises(ValueError,match='positive'): import_quotes(pd.DataFrame([row]).to_csv(index=False))


def test_imported_ui_preview_apply_and_discard(monkeypatch):
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest
    from engine import sample_orders
    from quotes import template
    import os
    monkeypatch.delenv('DEEPSEEK_API_KEY',raising=False)
    orders=sample_orders()
    now=datetime.now(timezone.utc)
    rows=[]
    codes={'Kuala Lumpur':'50000','George Town':'10000','Johor Bahru':'80000','Kota Kinabalu':'88000','Kuching':'93000','Sandakan':'90000'}
    for r in orders.to_dict('records'):
        rows.append({'quote_id':'Q'+r['order_id'],'provider':'Test Carrier','service':'Parcel','currency':'MYR','source_reference':'SYNTHETIC TEST','retrieved_at':now.isoformat(),'valid_until':(now+timedelta(days=1)).isoformat(),'origin_postcode':codes[r['origin']],'destination_postcode':codes[r['destination']],'origin_city':r['origin'],'destination_city':r['destination'],'origin_state':'TEST','destination_state':'TEST','physical_weight_kg':str(r['weight_kg']),'volumetric_weight_kg':'1','max_weight_kg':'100','max_length_cm':'100','max_width_cm':'100','max_height_cm':'100','eligible':'true','restrictions':'none','transport_method':'test','total_myr':'25.00','tax_myr':'0','surcharge_myr':'0','handling_myr':'0','last_mile_myr':'0','transit_days':'1','transit_guaranteed':'false','shipment_ids':r['order_id'],'conditions':'synthetic fixture'})
    data=pd.DataFrame(rows).to_csv(index=False).encode()
    class Upload:
        def getvalue(self): return data
    with patch('streamlit.file_uploader',return_value=Upload()):
        app=AppTest.from_file('/workspace/kargokawan.ai/app.py',default_timeout=30).run()
        app.radio[0].set_value('Imported quotations').run()
        next(b for b in app.button if b.label=='Load fictional demo postcodes').click().run()
        next(b for b in app.button if b.label=='Plan with imported quotations').click().run()
        assert not app.exception
        assert app.session_state['imported_preview']['plan']['total_myr']==375
        next(b for b in app.button if b.label=='Discard imported proposal').click().run()
        assert not app.session_state['imported_preview']
        next(b for b in app.button if b.label=='Plan with imported quotations').click().run()
        next(b for b in app.button if b.label=='Apply imported proposal').click().run()
        assert app.session_state['imported_approved']['total_myr']==375
        assert any(b.label=='Export approved imported manifest' for b in app.get('button')) or 'imported_approved' in app.session_state


@pytest.mark.parametrize('field,value', [('currency','USD'),('total_myr','-1'),('total_myr','abc'),('valid_until','bad'),('destination_postcode','1234'),('service','')])
def test_reject_invalid_quote_fields(field,value):
    now=datetime.now(timezone.utc)
    row={'quote_id':'Q','provider':'Carrier','service':'Parcel','currency':'MYR','source_reference':'SYNTHETIC','retrieved_at':now.isoformat(),'valid_until':(now+timedelta(days=1)).isoformat(),'origin_postcode':'01000','destination_postcode':'10000','origin_city':'Kuala Lumpur','destination_city':'George Town','origin_state':'Kedah','destination_state':'Penang','physical_weight_kg':'1','volumetric_weight_kg':'0.2','max_weight_kg':'2','max_length_cm':'20','max_width_cm':'20','max_height_cm':'20','eligible':'true','restrictions':'none','transport_method':'road','total_myr':'10.00','tax_myr':'0','surcharge_myr':'0','handling_myr':'0','last_mile_myr':'0','transit_days':'2','transit_guaranteed':'false','shipment_ids':'A','conditions':'standard'}
    row[field]=value
    with pytest.raises(ValueError): import_quotes(pd.DataFrame([row]).to_csv(index=False))
    row[field]='MYR' if field=='currency' else '10.00' if field=='total_myr' else (now+timedelta(days=1)).isoformat() if field=='valid_until' else '10000' if field=='destination_postcode' else 'Parcel'
    with pytest.raises(ValueError,match='Duplicate'): import_quotes(pd.DataFrame([row,row]).to_csv(index=False))
