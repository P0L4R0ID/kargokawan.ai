"""Conservative deterministic intake: parse labeled facts only, never infer missing fields."""
import re
import pandas as pd
from engine import CITIES
from delivery_operations import REQUIRED, checklist
from dashboard import normalize
from quotes import validate_postcodes

COLUMNS=('order_id','origin','destination','weight_kg','length_cm','width_cm','height_cm','deadline_days','recipient','origin_postcode','destination_postcode')

def extract(text):
    if not isinstance(text,str) or not text.strip(): return {'orders':pd.DataFrame(columns=COLUMNS),'notes':['Describe at least one order.'],'requested_quantity':None,'budget_myr':None}
    quantity=re.search(r'\b(\d+)\s+(?:orders?|parcels?|shipments?)\b',text,re.I)
    budget=re.search(r'\bbudget\s*(?:of|:|=)?\s*RM\s*(\d+(?:\.\d{1,2})?)\b',text,re.I)
    rows=[]; notes=[]
    for line in text.splitlines():
        if not line.strip(): continue
        row={key:'' for key in COLUMNS}
        m=re.search(r'^\s*(?:order|shipment)\s+(?:id\s*[:#-]?\s*)?([A-Za-z0-9_-]+)\s*:',line,re.I)
        if m: row['order_id']=m.group(1)
        m=re.search(r'\bfrom\s+([A-Za-z ]+?)(?=\s+(?:postcode|\d{5}|to\b)|[,;]|$)',line,re.I)
        if m and m.group(1).strip() in CITIES: row['origin']=m.group(1).strip()
        m=re.search(r'\bto\s+([A-Za-z ]+?)(?=\s+(?:postcode|\d{5}|recipient\b)|[,;]|$)',line,re.I)
        if m and m.group(1).strip() in CITIES: row['destination']=m.group(1).strip()
        m=re.search(r'\bfrom\s+[A-Za-z ]+?\s+(\d{5})\b',line,re.I)
        if m: row['origin_postcode']=m.group(1)
        m=re.search(r'\bto\s+[A-Za-z ]+?\s+(\d{5})\b',line,re.I)
        if m: row['destination_postcode']=m.group(1)
        m=re.search(r'\brecipient\s*[:=]?\s*([^,;]+)',line,re.I)
        if m: row['recipient']=m.group(1).strip()
        m=re.search(r'\b(\d+(?:\.\d+)?)\s*kg\b',line,re.I)
        if m: row['weight_kg']=m.group(1)
        m=re.search(r'\b(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*cm\b',line,re.I)
        if m: row['length_cm'],row['width_cm'],row['height_cm']=m.groups()
        m=re.search(r'\b(?:within|deadline\s*[:=]?)\s*(\d+)\s*days?\b',line,re.I)
        if m: row['deadline_days']=m.group(1)
        if row['order_id']: rows.append(row)
    if quantity and int(quantity.group(1))!=len(rows): notes.append(f'Request mentions {quantity.group(1)} orders but only {len(rows)} explicit order IDs were found. Enter each order separately.')
    if not rows: notes.append('No explicit order IDs found. Use one line per order, beginning with Order ID.')
    return {'orders':pd.DataFrame(rows,columns=COLUMNS),'notes':notes,'requested_quantity':int(quantity.group(1)) if quantity else None,'budget_myr':budget.group(1) if budget else None}

def followups(frame):
    rows=frame.to_dict('records') if hasattr(frame,'to_dict') else list(frame)
    questions=checklist(rows)
    for index,row in enumerate(rows,1):
        for field in ('origin','destination'):
            if not str(row.get(field,'')).strip(): questions.append(f'Order {index}: which {field} city?')
    return questions

def validate_draft(frame):
    questions=followups(frame)
    if questions: raise ValueError('Complete intake first: '+', '.join(questions[:6]))
    normalize(frame)
    validate_postcodes(frame)
    return frame.copy()
