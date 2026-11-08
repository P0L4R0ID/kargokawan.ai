"""Read the existing shipment columns plus operations intake fields from one CSV."""
import io
import pandas as pd
from dashboard import COLUMNS, normalize
from delivery_operations import REQUIRED, checklist
from quotes import validate_postcodes

EXTRA=('recipient','origin_postcode','destination_postcode')

def load_sample_intake(data):
    if isinstance(data,bytes): data=data.decode('utf-8-sig')
    frame=pd.read_csv(io.StringIO(data),dtype={'order_id':str,'origin_postcode':str,'destination_postcode':str},keep_default_na=False)
    missing=[field for field in (*COLUMNS,*EXTRA) if field not in frame]
    if missing: raise ValueError('Missing intake CSV columns: '+', '.join(missing))
    if frame.empty or len(frame)>20: raise ValueError('Provide between 1 and 20 orders.')
    return frame

def validate_complete(data):
    frame=load_sample_intake(data)
    tasks=checklist(frame.to_dict('records'))
    if tasks: raise ValueError('Missing order information: '+', '.join(tasks))
    normalize(frame)
    validate_postcodes(frame)
    return frame
