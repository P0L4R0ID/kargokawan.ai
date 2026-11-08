"""Provenance-preserving tariff estimates; no carrier APIs or fictional fallback."""
import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_CEILING

SCHEMAS={
 'carriers': 'carrier_id name service available provenance source_reference',
 'rate_cards': 'carrier_id service version origin_zone destination_zone min_weight_kg max_weight_kg rate_myr currency effective_from valid_until provenance source_reference',
 'pricing_rules': 'carrier_id service version volumetric_divisor_cm3_per_kg weight_increment_kg minimum_charge_myr tax_rate_pct fee_myr surcharge_myr max_length_cm max_width_cm max_height_cm effective_from valid_until provenance source_reference',
 'postcode_zones': 'carrier_id postcode zone effective_from valid_until provenance source_reference',
}
FIELDS={k:v.split() for k,v in SCHEMAS.items()}
DECIMAL_FIELDS={'min_weight_kg','max_weight_kg','rate_myr','volumetric_divisor_cm3_per_kg','weight_increment_kg','minimum_charge_myr','tax_rate_pct','fee_myr','surcharge_myr','max_length_cm','max_width_cm','max_height_cm'}
DATE_FIELDS={'effective_from','valid_until'}

def template(kind):
    out=io.StringIO(); csv.writer(out).writerow(FIELDS[kind]); return out.getvalue()

def load_csv(kind,data):
    if kind not in FIELDS: raise ValueError('Unknown tariff table.')
    if isinstance(data,bytes): data=data.decode('utf-8-sig')
    reader=csv.DictReader(io.StringIO(data))
    if not reader.fieldnames or set(reader.fieldnames)!=set(FIELDS[kind]) or len(reader.fieldnames)!=len(set(reader.fieldnames)): raise ValueError('Invalid tariff columns.')
    rows=[]
    for raw in reader:
        if None in raw or any(v is None or not v.strip() for v in raw.values()): raise ValueError('Missing tariff value.')
        row={k:v.strip() for k,v in raw.items()}
        if row['provenance'] not in ('synthetic','official_rate_card'): raise ValueError('Provenance must be synthetic or official_rate_card.')
        if row['provenance']=='official_rate_card' and not row['source_reference'].startswith('https://'): raise ValueError('Official tariff needs a source URL.')
        if kind=='carriers':
            if row['available'].lower() not in ('true','false'): raise ValueError('Invalid availability.')
            row['available']=row['available'].lower()=='true'
        if kind=='rate_cards' and row['currency']!='MYR': raise ValueError('Only MYR tariffs supported.')
        if kind=='postcode_zones' and not re.fullmatch(r'\d{5}',row['postcode']): raise ValueError('Invalid Malaysian postcode.')
        for field in DATE_FIELDS & row.keys():
            try: row[field]=date.fromisoformat(row[field])
            except ValueError: raise ValueError('Invalid tariff date.')
        if 'effective_from' in row and row['effective_from']>row['valid_until']: raise ValueError('Invalid tariff validity.')
        for field in DECIMAL_FIELDS & row.keys():
            try: row[field]=Decimal(row[field])
            except InvalidOperation: raise ValueError('Invalid tariff number.')
            if not row[field].is_finite() or row[field]<0: raise ValueError('Invalid tariff number.')
        if kind=='rate_cards' and (row['min_weight_kg']>=row['max_weight_kg'] or row['rate_myr']<=0): raise ValueError('Invalid weight band or rate.')
        if kind=='pricing_rules' and (row['volumetric_divisor_cm3_per_kg']<=0 or row['weight_increment_kg']<=0 or row['tax_rate_pct']>100 or any(row[x]<=0 for x in ('max_length_cm','max_width_cm','max_height_cm'))): raise ValueError('Invalid pricing rule.')
        rows.append(row)
    if not rows: raise ValueError('Empty tariff table.')
    return rows

def calculate(order,tables,as_of=None):
    """Return an estimate or RATE UNAVAILABLE; do not infer missing tariff data."""
    day=as_of or date.today()
    try:
        origin=str(order['origin_postcode']); destination=str(order['destination_postcode'])
        if not re.fullmatch(r'\d{5}',origin) or not re.fullmatch(r'\d{5}',destination): raise ValueError('Postcode missing or invalid.')
        weight=Decimal(str(order['weight_kg']))
        dims=[Decimal(str(order[x])) for x in ('length_cm','width_cm','height_cm')]
        if weight<=0 or any(x<=0 for x in dims): raise ValueError('Invalid dimensions or weight.')
    except (KeyError,InvalidOperation,ValueError) as exc: return {'status':'RATE UNAVAILABLE','reason':str(exc)}
    results=[]
    active=lambda r: r.get('effective_from',day)<=day<=r.get('valid_until',day)
    for carrier in tables['carriers']:
        if not carrier['available']: continue
        key=(carrier['carrier_id'],carrier['service'])
        rules=[r for r in tables['pricing_rules'] if (r['carrier_id'],r['service'])==key and active(r)]
        if len(rules)!=1: continue
        rule=rules[0]
        if any(d>rule['max_'+name] for d,name in zip(dims,('length_cm','width_cm','height_cm'))): continue
        zones=[]
        for postcode in (origin,destination):
            matches={r['zone'] for r in tables['postcode_zones'] if r['carrier_id']==key[0] and r['postcode']==postcode and active(r)}
            if len(matches)!=1: break
            zones.append(next(iter(matches)))
        if len(zones)!=2: continue
        volume=dims[0]*dims[1]*dims[2]/rule['volumetric_divisor_cm3_per_kg']
        increment=rule['weight_increment_kg']
        chargeable=(max(weight,volume)/increment).to_integral_value(rounding=ROUND_CEILING)*increment
        cards=[r for r in tables['rate_cards'] if (r['carrier_id'],r['service'])==key and r['version']==rule['version'] and r['origin_zone']==zones[0] and r['destination_zone']==zones[1] and r['min_weight_kg']<chargeable<=r['max_weight_kg'] and active(r)]
        if len(cards)!=1: continue
        card=cards[0]
        subtotal=max(card['rate_myr'],rule['minimum_charge_myr'])+rule['fee_myr']+rule['surcharge_myr']
        tax=(subtotal*rule['tax_rate_pct']/100).quantize(Decimal('.01'))
        total=(subtotal+tax).quantize(Decimal('.01'))
        results.append({'status':'CALCULATED ESTIMATE','carrier_id':key[0],'service':key[1],'version':rule['version'],'source_type':'calculated_estimate','provenance':card['provenance'],'source_reference':card['source_reference'],'rule_source':rule['source_reference'],'zones':zones,'physical_kg':weight,'volumetric_kg':volume,'chargeable_kg':chargeable,'base_myr':card['rate_myr'],'minimum_myr':rule['minimum_charge_myr'],'fee_myr':rule['fee_myr'],'surcharge_myr':rule['surcharge_myr'],'tax_myr':tax,'total_myr':total,'valid_until':min(card['valid_until'],rule['valid_until'])})
    return results if results else {'status':'RATE UNAVAILABLE','reason':'No complete applicable rate card, rule and postcode zones.'}
