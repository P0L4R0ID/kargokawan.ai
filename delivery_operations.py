"""Local delivery-job lifecycle. No carrier side effects."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from mixed_method import optimize, preview as plan_preview, approve as plan_approve
from focused_quotes import fingerprint

STATES=('DRAFT','NEEDS_INFORMATION','READY_FOR_REVIEW','APPROVED','PREPARED','AWAITING_BOOKING','BOOKED','IN_TRANSIT','DELIVERED','NEEDS_ATTENTION','FAILED','CANCELLED')
TRANSITIONS={'DRAFT':{'NEEDS_INFORMATION','READY_FOR_REVIEW','CANCELLED'},'NEEDS_INFORMATION':{'READY_FOR_REVIEW','CANCELLED'},'READY_FOR_REVIEW':{'APPROVED','NEEDS_INFORMATION','CANCELLED'},'APPROVED':{'PREPARED','READY_FOR_REVIEW','CANCELLED'},'PREPARED':{'AWAITING_BOOKING','READY_FOR_REVIEW','CANCELLED'},'AWAITING_BOOKING':{'BOOKED','READY_FOR_REVIEW','CANCELLED'},'BOOKED':{'IN_TRANSIT','NEEDS_ATTENTION','FAILED','CANCELLED'},'IN_TRANSIT':{'DELIVERED','NEEDS_ATTENTION','FAILED'},'NEEDS_ATTENTION':{'IN_TRANSIT','FAILED','CANCELLED'},'FAILED':set(),'CANCELLED':set(),'DELIVERED':set()}
REQUIRED=('order_id','recipient','origin_postcode','destination_postcode','weight_kg','length_cm','width_cm','height_cm','deadline_days')

def checklist(orders):
    items=[]
    for number,row in enumerate(orders,1):
        for field in REQUIRED:
            if row.get(field) is None or str(row.get(field)).strip()=='': items.append(f'Order {number}: supply {field}')
        for field in ('origin_postcode','destination_postcode'):
            if row.get(field) and (len(str(row[field]))!=5 or not str(row[field]).isdigit()): items.append(f'Order {number}: correct {field} to five digits')
    ids=[str(row.get('order_id','')) for row in orders]
    if len(ids)!=len(set(ids)): items.append('Use unique order IDs')
    return items

class JobStore:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, state TEXT NOT NULL, orders_json TEXT NOT NULL, quotes_json TEXT NOT NULL, unavailable_json TEXT NOT NULL, proposal_json TEXT, booking_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, evidence TEXT NOT NULL)')
    def _db(self): return sqlite3.connect(self.path)
    def _event(self,db,job_id,actor,action,evidence=''):
        db.execute('INSERT INTO events(job_id,at,actor,action,evidence) VALUES (?,?,?,?,?)',(job_id,datetime.now(timezone.utc).isoformat(),actor,action,evidence))
    def create(self,orders):
        job_id='KK-'+uuid.uuid4().hex[:12].upper();now=datetime.now(timezone.utc).isoformat()
        rows=orders.to_dict('records') if hasattr(orders,'to_dict') else list(orders)
        state='NEEDS_INFORMATION' if checklist(rows) else 'DRAFT'
        with self._db() as db:
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)',(job_id,state,json.dumps(rows,default=str),'[]','[]',None,None,now,now))
            self._event(db,job_id,'user','CREATED',state)
        return job_id
    def get(self,job_id):
        with self._db() as db:
            row=db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()
            if not row: raise ValueError('Unknown job ID.')
            events=db.execute('SELECT at,actor,action,evidence FROM events WHERE job_id=? ORDER BY id',(job_id,)).fetchall()
        keys=('job_id','state','orders_json','quotes_json','unavailable_json','proposal_json','booking_json','created_at','updated_at')
        value=dict(zip(keys,row));value['orders']=json.loads(value.pop('orders_json'));value['quotes']=json.loads(value.pop('quotes_json'));value['unavailable']=json.loads(value.pop('unavailable_json'));value['proposal']=json.loads(value.pop('proposal_json')) if value['proposal_json'] else None;value['booking']=json.loads(value.pop('booking_json')) if value['booking_json'] else None;value['events']=[dict(zip(('at','actor','action','evidence'),x)) for x in events]
        return value
    def transition(self,job_id,target,actor='user',evidence=''):
        job=self.get(job_id)
        if target not in TRANSITIONS[job['state']]: raise ValueError('Invalid job state transition.')
        if target in ('BOOKED','IN_TRANSIT','DELIVERED') and not evidence.strip(): raise ValueError('External status requires explicit evidence.')
        with self._db() as db:
            db.execute('UPDATE jobs SET state=?,updated_at=? WHERE job_id=?',(target,datetime.now(timezone.utc).isoformat(),job_id))
            self._event(db,job_id,actor,target,evidence)
    def set_inputs(self,job_id,orders,quotes,unavailable=()):
        job=self.get(job_id)
        if job['state'] in ('BOOKED','IN_TRANSIT','DELIVERED'): raise ValueError('Booked shipments cannot be silently changed.')
        rows=orders.to_dict('records') if hasattr(orders,'to_dict') else list(orders)
        state='NEEDS_INFORMATION' if checklist(rows) else 'DRAFT'
        with self._db() as db:
            db.execute('UPDATE jobs SET state=?,orders_json=?,quotes_json=?,unavailable_json=?,proposal_json=NULL,booking_json=NULL,updated_at=? WHERE job_id=?',(state,json.dumps(rows,default=str),json.dumps(quotes,default=str),json.dumps(list(unavailable)),datetime.now(timezone.utc).isoformat(),job_id))
            self._event(db,job_id,'user','INPUTS_UPDATED','Prior proposal invalidated')
    def propose(self,job_id,orders,quotes,unavailable=()):
        job=self.get(job_id)
        if job['state'] in ('BOOKED','IN_TRANSIT','DELIVERED'): raise ValueError('Booked shipments cannot be silently replanned.')
        rows=orders.to_dict('records') if hasattr(orders,'to_dict') else list(orders)
        missing=checklist(rows)
        if missing: raise ValueError('Missing order information: '+', '.join(missing[:5]))
        result=plan_preview(orders,quotes,unavailable)
        snapshot=fingerprint(orders,quotes,[])+repr(sorted(unavailable))
        with self._db() as db:
            db.execute('UPDATE jobs SET state=?,orders_json=?,quotes_json=?,unavailable_json=?,proposal_json=?,updated_at=? WHERE job_id=?',('READY_FOR_REVIEW',json.dumps(rows,default=str),json.dumps(quotes,default=str),json.dumps(list(unavailable)),json.dumps({'fingerprint':snapshot,'summary':{'total_myr':str(result['result']['total_myr']),'quote_ids':[x['quote_id'] for x in result['result']['selected']],'decisions':[{'quote_id':x['quote_id'],'provider':x['provider'],'method':x['transport_method'],'shipment_ids':list(x['shipment_ids']),'source_reference':x['source_reference']} for x in result['result']['selected']]}},default=str),datetime.now(timezone.utc).isoformat(),job_id))
            self._event(db,job_id,'agent','PLAN_PROPOSED','No booking')
        return result
    def approve(self,job_id,orders,quotes,unavailable=()):
        job=self.get(job_id)
        if job['state']!='READY_FOR_REVIEW' or not job['proposal']: raise ValueError('No reviewable proposal.')
        if job['proposal']['fingerprint']!=fingerprint(orders,quotes,[])+repr(sorted(unavailable)): raise ValueError('Inputs changed; generate a fresh proposal.')
        result=plan_approve({'fingerprint':job['proposal']['fingerprint']},orders,quotes,unavailable)
        self.transition(job_id,'APPROVED','user','Explicit approval of '+', '.join(job['proposal']['summary']['quote_ids']))
        return result
    def record_booking(self,job_id,provider_reference,tracking_id,evidence):
        job=self.get(job_id)
        if job['state']!='AWAITING_BOOKING': raise ValueError('Booking confirmation requires an approved prepared job.')
        if not all(str(x).strip() for x in (provider_reference,tracking_id,evidence)): raise ValueError('Booking reference, tracking ID and evidence are required.')
        with self._db() as db:
            db.execute('UPDATE jobs SET booking_json=? WHERE job_id=?',(json.dumps({'provider_reference':provider_reference,'tracking_id':tracking_id,'evidence':evidence}),job_id))
        self.transition(job_id,'BOOKED','user',evidence)
    def manifest(self,job_id):
        job=self.get(job_id)
        if job['state'] not in ('APPROVED','PREPARED','AWAITING_BOOKING','BOOKED','IN_TRANSIT','DELIVERED'): raise ValueError('Approve a plan before export.')
        decisions=job['proposal']['summary']['decisions']
        rows=[]
        for r in job['orders']:
            match=next(d for d in decisions if str(r['order_id']) in d['shipment_ids'])
            rows.append({'Job ID':job_id,'Order ID':r['order_id'],'Recipient':r['recipient'],'Origin postcode':r['origin_postcode'],'Destination postcode':r['destination_postcode'],'Deadline days':r['deadline_days'],'Selected provider':match['provider'],'Method':match['method'],'Quote ID':match['quote_id'],'Source reference':match['source_reference'],'Status':'PROPOSAL — NOT A BOOKING'})
        return pd.DataFrame(rows)
