from pathlib import Path
from datetime import date
from decimal import Decimal
from pricing import load_csv, calculate, FIELDS

ROOT=Path(__file__).resolve().parents[1]/'data/pricing/synthetic'
def tables(): return {kind:load_csv(kind,(ROOT/(kind+'.csv')).read_text()) for kind in FIELDS}
ORDER={'origin_postcode':'50000','destination_postcode':'10000','weight_kg':1,'length_cm':20,'width_cm':20,'height_cm':20}
def test_synthetic_tariff_breakdown_and_separation():
    result=calculate(ORDER,tables(),date(2026,11,8))[0]
    assert result['chargeable_kg']==Decimal('2.0')
    assert result['total_myr']==Decimal('15.00')
    assert result['source_type']=='calculated_estimate' and result['provenance']=='synthetic'

def test_unavailable_for_missing_zone_band_expiry_and_size():
    for field, value in [('destination_postcode','90000'),('weight_kg',6),('length_cm',200)]:
        assert calculate({**ORDER,field:value},tables(),date(2026,11,8))['status']=='RATE UNAVAILABLE'
    assert calculate(ORDER,tables(),date(2028,1,1))['status']=='RATE UNAVAILABLE'

def test_reject_unknown_currency_and_missing_rule():
    value=(ROOT/'rate_cards.csv').read_text().replace('MYR','USD')
    try: load_csv('rate_cards',value)
    except ValueError: pass
    else: assert False
    data=tables();data['pricing_rules']=[]
    assert calculate(ORDER,data,date(2026,11,8))['status']=='RATE UNAVAILABLE'
