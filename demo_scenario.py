"""Explicitly synthetic Malaysian example; values are never carrier quotations."""
import json
from datetime import datetime,timezone,timedelta
import pandas as pd
from hybrid_quotes import normalize

LABEL='SIMULATED DEMO — NOT REAL CARRIER PRICES'

def load_demo():
    orders=pd.DataFrame([{'order_id':oid,'origin_postcode':'50000','destination_postcode':postcode,'weight_kg':weight,'length_cm':20,'width_cm':15,'height_cm':10,'deadline_days':2} for oid,postcode,weight in [('D1','50000',1),('D2','46000',2),('D3','43000',1),('D4','40000',2)]])
    now=datetime.now(timezone.utc)
    common={'source_class':'SYNTHETIC','origin_postcode':'50000','pickup_location':'Fictional KL pickup','length_cm':'50','width_cm':'50','height_cm':'50','capacity_kg':'10','full_cost':'true','tax_status':'included','surcharge_status':'included','source_reference':LABEL,'collected_at':now.isoformat(),'valid_until':(now+timedelta(days=1)).isoformat(),'transit_days':'1','restrictions':'none'}
    quotes=[]
    for oid,postcode,weight in [('D1','50000',1),('D2','46000',2),('D3','43000',1),('D4','40000',2)]:
        quotes.append(normalize({**common,'quote_id':'SYN-C-'+oid,'provider':'Synthetic EasyParcel example','service':'Synthetic parcel','transport_method':'parcel_courier','destination_postcode':postcode,'dropoff_locations':'','shipment_ids':oid,'physical_weight_kg':str(weight),'displayed_cost_myr':'20.00'}))
    stops=[{'shipment_id':oid,'postcode':postcode,'sequence':i} for i,(oid,postcode) in enumerate([('D1','50000'),('D2','46000'),('D3','43000')],1)]
    quotes.append(normalize({**common,'quote_id':'SYN-V-123','provider':'Synthetic Lalamove example','service':'Synthetic multi-stop van','transport_method':'multi_stop_vehicle','destination_postcode':'50000','dropoff_locations':json.dumps(stops),'shipment_ids':'D1;D2;D3','physical_weight_kg':'4','displayed_cost_myr':'35.00'}))
    return orders,quotes
