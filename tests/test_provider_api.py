from urllib.error import HTTPError
from carrier_adapters import EasyParcelAdapter, LalamoveAdapter, EASYPARCEL_RATE_URL
from agent import ProviderQuoteTools

ORDER={'order_id':'DEMO-1','origin_postcode':'05000','destination_postcode':'88000',
       'origin_state':'Kedah','destination_state':'Sabah','weight_kg':2,
       'length_cm':20,'width_cm':10,'height_cm':5}
RESPONSE={'api_status':'Success','result':[{'status':'Success','rates':[
    {'member_rate':[{'rate_id':'R1','courier_name':'Test Courier','service_name':'Parcel',
                     'price':'12.50','shipment_price':'10.00','addon_price':'2.50','delivery':'2-4 days'}],
     'non_member_rate':[{'rate_id':'R2','price':'16.00'}]}]}]}

def test_missing_credentials(monkeypatch):
    assert EasyParcelAdapter(secrets={}).fetch_rates(ORDER)['status']=='NOT_CONNECTED'
    assert LalamoveAdapter(secrets={}).fetch_rates({})['status']=='NOT_CONNECTED'

def test_authenticated_response_is_incomplete(monkeypatch):
    def transport(url, fields, timeout):
        assert url==EASYPARCEL_RATE_URL and timeout==10
        assert fields['api']=='test-secret'
        assert fields['bulk[0][pick_code]']=='05000'
        assert fields['bulk[0][send_country]']=='MY'
        return RESPONSE
    result=EasyParcelAdapter(secrets={'EASYPARCEL_API_KEY':'test-secret'},transport=transport).fetch_rates(ORDER)
    assert result['status']=='CONNECTED'
    assert len(result['quotes'])==2
    assert {q['account_tier'] for q in result['quotes']}=={'member_rate','non_member_rate'}
    assert all(q['source_class']=='LIVE_AUTHENTICATED' and q['review_status']=='INCOMPLETE' and not q['full_cost'] for q in result['quotes'])
    assert all(q['valid_until'] is None and q['tax_status']=='UNKNOWN' and q['surcharge_status']=='UNKNOWN' for q in result['quotes'])

def test_errors_are_sanitized():
    for exception, term in [(HTTPError('url',403,'secret',None,None),'Authentication'),
                            (HTTPError('url',429,'secret',None,None),'Rate limit'),
                            (TimeoutError('secret'),'timed out')]:
        def fail(*args): raise exception
        result=EasyParcelAdapter(secrets={'EASYPARCEL_API_KEY':'test-secret'},transport=fail).fetch_rates(ORDER)
        assert result['status']=='ERROR' and term in result['reason'] and 'secret' not in result['reason']

def test_no_calls_on_incomplete_order():
    def fail(*args): raise AssertionError('request should not be sent')
    result=EasyParcelAdapter(secrets={'EASYPARCEL_API_KEY':'test-secret'},transport=fail).fetch_rates({**ORDER,'origin_state':''})
    assert result['status']=='ERROR'

def test_lalamove_needs_real_stops_and_does_not_call():
    adapter=LalamoveAdapter(secrets={'LALAMOVE_API_KEY':'test','LALAMOVE_API_SECRET':'test'})
    assert adapter.fetch_rates({'stops':[{'postcode':'05000'},{'postcode':'05100'}]})['status']=='ERROR'
    assert adapter.fetch_rates({'stops':[{'address':'A','coordinates':{'lat':1,'lng':2}},
                                        {'address':'B','coordinates':{'lat':3,'lng':4}}]})['quotes']==[]

def test_bounded_read_only_tools():
    tool=ProviderQuoteTools(EasyParcelAdapter(secrets={}))
    assert 'origin_state' in tool.call('needed_quote_facts',ORDER|{'origin_state':''})['missing']
    assert tool.call('connection_status')['status']=='NOT_CONNECTED'
    assert tool.call('fetch_easyparcel_rates',ORDER)['quotes']==[]
    for _ in range(3): tool.call('connection_status')
    import pytest
    with pytest.raises(ValueError,match='limit'): tool.call('connection_status')
