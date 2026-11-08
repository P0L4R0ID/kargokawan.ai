import io
import hashlib
import pandas as pd
import streamlit as st
from engine import sample_orders, CITIES
from dashboard import PROVIDERS, COLUMNS, normalize, replan, manifest
from agent import run_request, approve
from ai_provider import configuration, test_connection

st.set_page_config(page_title='KargoKawan | Operations', page_icon='📦', layout='wide')
st.markdown('''<style>
.stApp {background: #f5f7fb;} h1,h2,h3 {color:#123b49;}
[data-testid="stMetric"] {background:white;border:1px solid #dce6eb;border-radius:12px;padding:18px;}
[data-testid="stSidebar"] {background:#eaf1f4;}
</style>''', unsafe_allow_html=True)
st.caption('KARGOKAWAN AI  /  MALAYSIA SME OPERATIONS')
st.title('Deliver smarter. Stay in control.')
st.write('Plan shipments, compare delivery strategies and respond to operational changes.')
from pilot_ui import render as render_pilot
render_pilot()
st.header('Public fictional demo')
st.warning('SIMULATION ONLY · All shipping providers are fictional. Rates, costs, ETAs and savings are simulated assumptions, not quotations or guarantees. No bookings or payments.')
for key, value in {'orders':sample_orders(), 'planner':{}, 'revision':0, 'upload_hash':None}.items():
    if key not in st.session_state: st.session_state[key] = value
s = st.session_state
with st.sidebar:
    st.header('Operations desk')
    st.caption('36-hour competition prototype')
    disabled = st.multiselect('Unavailable fictional providers', PROVIDERS, key='provider_state', help='Changes automatically trigger replanning after the initial run.')
    st.divider()
    upload = st.file_uploader('Import shipment CSV', type=['csv'])
    st.download_button('Download sample CSV', sample_orders().to_csv(index=False), 'sample_orders.csv', 'text/csv')
    if upload is not None:
        digest = hashlib.sha256(upload.getvalue()).hexdigest()
        if digest != s.upload_hash:
            s.upload_hash = digest
            try:
                s.orders = normalize(pd.read_csv(io.BytesIO(upload.getvalue()), dtype={'order_id':str}))
                s.revision += 1
            except (ValueError, UnicodeError) as exc:
                st.error(f'Import rejected; existing orders retained: {exc}')
    else:
        s.upload_hash = None
    if st.button('Restore demo orders'):
        s.orders = sample_orders(); s.revision += 1
    st.caption('12 Malaysian cities · Up to 20 orders · MYR')

st.subheader('Shipment workspace')
st.caption('Edit deadlines or orders directly. After the first plan, each committed edit or provider change automatically replans.')
edited = st.data_editor(s.orders, key=f'orders_{s.revision}', num_rows='dynamic', hide_index=True,
    use_container_width=True, column_config={
        'origin':st.column_config.SelectboxColumn('Origin', options=list(CITIES), required=True),
        'destination':st.column_config.SelectboxColumn('Destination', options=list(CITIES), required=True),
        'deadline_days':st.column_config.NumberColumn('Deadline (days)', min_value=1, step=1),
    })
run = st.button('Plan shipments', type='primary')
if run or s.planner.get('signature'):
    with st.spinner('Evaluating simulated delivery strategies…'):
        replan(s.planner, edited, disabled, force=run)
if s.planner.get('error'):
    st.error('No current manifest: ' + s.planner['error'])
    st.info('Correct the orders or restore provider availability. The planner will retry automatically on change.')
result = s.planner.get('result')
if result:
    a,b,c,d = st.columns(4)
    a.metric('Simulated optimized cost', f'RM {result["total"]:,.2f}')
    b.metric('Simulated standalone baseline', f'RM {result["baseline_cost"]:,.2f}' if result['baseline_cost'] is not None else 'Unavailable')
    c.metric('Simulated cost difference', f'RM {result["savings"]:,.2f}' if result['savings'] is not None else 'Unavailable')
    d.metric('Delivery groups', len(result['selected']))
    plan_tab, compare_tab, audit_tab = st.tabs(['Delivery plan', 'Cost comparison', 'Decisions & audit'])
    with plan_tab:
        st.dataframe(manifest(result), hide_index=True, use_container_width=True)
        st.download_button('Export simulated CSV manifest', manifest(result).to_csv(index=False).encode('utf-8-sig'), 'kargokawan_simulated_manifest.csv', 'text/csv')
    with compare_tab:
        st.caption('Baseline: cheapest eligible standalone service per order under the same deadlines and availability. Differences are modelled, not guaranteed savings.')
        if result['baseline_cost'] is not None:
            st.bar_chart(pd.DataFrame({'Simulated cost (RM)':[result['baseline_cost'], result['total']]}, index=['Standalone', 'Optimized']))
            st.dataframe(manifest({'selected':result['baseline']}), hide_index=True)
        else: st.info('A complete standalone baseline is unavailable under the current constraints.')
    with audit_tab:
        st.write(f'{result["candidate_count"]} eligible strategies evaluated. Solver: {result["status"]}')
        st.caption('The deterministic solver minimizes combined simulated cost subject to exact coverage and deadlines. Availability and deadline constraints exclude options; group shipments share origin and destination. Solver time and gap limits mean exact optimality is not guaranteed.')
        for plan in result['selected']:
            with st.expander(f'{", ".join(plan.ids)} · {plan.kind} · simulated RM {plan.cost:,.2f}'):
                st.write(f'Fictional provider: {plan.provider}. Simulated ETA: {plan.eta_days} days.')
                st.write(plan.note)
                st.write('Selected as part of the lowest-cost complete feasible plan found, rather than evaluating each order in isolation.')
else:
    st.info('Import a CSV or use the editable Malaysian sample orders, then select Plan shipments.')
if s.planner.get('history'):
    st.subheader('Decision audit trail')
    st.caption('Session-only history · timestamps in UTC · input snapshots included for review')
    for i,event in reversed(list(enumerate(s.planner['history'], 1))):
        with st.expander(f'{i:02d} · {event["status"]} · {event["trigger"]} · {event["time"]}'):
            if event['delta'] is not None: st.write(f'Simulated change from prior plan: RM {event["delta"]:+,.2f}')
            for step in event['steps']: st.write('• ' + step)
            st.write('Unavailable fictional providers:', ', '.join(event['disabled']) or 'None')
            st.code(event['input_csv'], language='csv')


st.subheader('AI Logistics Assistant')
st.caption('SIMULATED DATA · Fictional shipping only · Up to six tool calls · Changes require approval')
config = configuration()
st.write(f"Selected AI provider: {config['provider']} · Model: {config['model']}")
st.caption('Live API configured (connection unverified)' if config['ready'] else 'Deterministic fallback active — no usable provider configuration')
st.caption('Live mode sends requests and computed data to the selected AI provider. Use fictional/anonymized data only; never send customer personal information.')
if st.button('Test AI connection'):
    with st.spinner('Testing one read-only tool call on fictional samples…'):
        s.ai_connection = test_connection()
if s.get('ai_connection'):
    (st.success if s.ai_connection['ok'] else st.warning)(s.ai_connection['message'])
request = st.text_input('Ask the logistics assistant', placeholder='Optimise these orders and explain why this plan is cheaper.')
if st.button('Ask assistant'):
    try:
        with st.spinner('Running logistics tools…'):
            s.assistant_result = run_request(request, edited, disabled)
    except ValueError as exc:
        s.pop('assistant_result', None)
        st.error(str(exc))


def apply_assistant_change():
    try:
        updated, unavailable = approve(s.assistant_result['proposal'], edited, disabled, approved=True)
        s.orders = updated
        s.provider_state = unavailable
        s.revision += 1
        replan(s.planner, updated, unavailable, force=True)
        s.planner['history'][-1]['trigger'] = 'User approved AI assistant disruption preview'
        s.pop('assistant_result', None)
        s.assistant_feedback = 'Approved change applied and replanned.'
    except ValueError as exc:
        s.assistant_feedback = str(exc)


def discard_assistant_change():
    s.pop('assistant_result', None)
    s.assistant_feedback = 'Proposal discarded. Current orders and providers were not changed.'


if s.get('assistant_feedback'):
    st.info(s.assistant_feedback)
answer = s.get('assistant_result')
if answer:
    st.write(answer['label'] + ' · ' + answer['provider'] + ' · ' + answer['mode'])
    if answer['notice']: st.info(answer['notice'])
    for number, action in enumerate(answer['trace'], 1):
        with st.expander(f"{number}. {action['tool']} — {action['status']}", expanded=True):
            st.json(action.get('result', {'error':action.get('error')}))
    if answer['plan']:
        st.write('Computed current plan — SIMULATED DATA')
        st.json(answer['plan'])
    if answer['proposal']:
        proposal = answer['proposal']
        st.warning('Preview only. Current orders and availability remain unchanged until you approve.')
        left, right = st.columns(2)
        left.write('Before — SIMULATED DATA'); left.json(proposal['before'])
        right.write('Proposed — SIMULATED DATA'); right.json(proposal['after'])
        st.button('Apply proposed change', on_click=apply_assistant_change)
        st.button('Discard', on_click=discard_assistant_change)


from quotes import template, import_quotes, validate_postcodes, preview_imported, approve_imported, imported_manifest
st.subheader('Quotation data source')
quote_mode = st.radio('Select price source', ['Simulated demo', 'Imported quotations'], horizontal=True)
if quote_mode == 'Imported quotations':
    st.warning('USER-SUPPLIED quotations are not independently authenticated. No booking or payment occurs.')
    st.download_button('Download quotation CSV template', template(), 'quotation_template.csv', 'text/csv')
    st.caption('Enter five-digit postcodes for each order. Sample values below are fictional demo input.')
    demo_postcodes = {'Kuala Lumpur':'50000','George Town':'10000','Johor Bahru':'80000','Ipoh':'30000','Melaka':'75000','Kuantan':'25000','Kota Kinabalu':'88000','Sandakan':'90000','Tawau':'91000','Kuching':'93000','Miri':'98000','Sibu':'96000'}
    real_orders = edited.copy()
    if 'imported_orders' not in s or not s.imported_orders[COLUMNS].equals(edited[COLUMNS]):
        s.imported_orders = edited.copy()
        s.imported_orders['origin_postcode'] = ''
        s.imported_orders['destination_postcode'] = ''
        s.imported_preview = None
        s.imported_approved = None
    real_orders = s.imported_orders.copy()
    if st.button('Load fictional demo postcodes'):
        s.imported_orders['origin_postcode'] = s.imported_orders.origin.map(demo_postcodes)
        s.imported_orders['destination_postcode'] = s.imported_orders.destination.map(demo_postcodes)
        s.real_postcode_revision = s.get('real_postcode_revision', 0) + 1
        real_orders = s.imported_orders.copy()
    real_orders = st.data_editor(real_orders, key=f'real_orders_editor_{s.get("real_postcode_revision",0)}', hide_index=True, use_container_width=True)
    if not real_orders.equals(s.imported_orders):
        s.imported_orders = real_orders.copy()
        s.imported_preview = None
        s.imported_approved = None
    quote_upload = st.file_uploader('Upload user-obtained quotation CSV', type=['csv'], key='quote_upload')
    unavailable = st.multiselect('Unavailable quoted providers', [], key='quoted_unavailable')
    if tuple(unavailable) != s.get('imported_unavailable', ()):
        s.imported_unavailable = tuple(unavailable)
        s.imported_preview = None
        s.imported_approved = None
    imported = None
    upload_bytes = quote_upload.getvalue() if quote_upload is not None else None
    if upload_bytes != s.get('imported_upload_bytes'):
        s.imported_upload_bytes = upload_bytes
        s.imported_preview = None
        s.imported_approved = None
    if quote_upload is not None:
        try:
            imported = import_quotes(upload_bytes)
            st.dataframe(pd.DataFrame([{'Quote ID':q['quote_id'],'Provider':q['provider'],'Service':q['service'],'Price MYR':str(q['total_myr']),'Reference':q['source_reference'],'Retrieved':q['retrieved_at'].isoformat(),'Expires':q['valid_until'].isoformat(),'Eligible':q['eligible']} for q in imported]))
        except ValueError as exc:
            st.error(str(exc))
    if st.button('Plan with imported quotations'):
        try:
            if imported is None: raise ValueError('Upload valid quotations first.')
            s.imported_preview = preview_imported(real_orders, imported, unavailable)
            s.imported_approved = None
        except ValueError as exc:
            s.imported_preview = None
            st.error(str(exc))
    if s.get('imported_preview') and imported is not None and s.imported_preview['fingerprint'] != __import__('quotes').quote_fingerprint(validate_postcodes(real_orders), imported, unavailable):
        s.imported_preview = None
        s.imported_approved = None
        st.warning('Inputs changed. Generate a fresh preview.')
    if s.get('imported_preview'):
        proposed = s.imported_preview['plan']
        st.info('Preview only. Review quote IDs and source references before approval.')
        st.metric('Quoted proposal MYR', str(proposed['total_myr']))
        st.metric('Same-source standalone baseline MYR', str(proposed['baseline_myr']) if proposed['baseline_myr'] is not None else 'UNKNOWN / NOT QUOTED')
        st.dataframe(imported_manifest(proposed))
        if st.button('Apply imported proposal'):
            try:
                if imported is None: raise ValueError('Quotations changed; generate a fresh preview.')
                s.imported_approved = approve_imported(s.imported_preview, real_orders, imported, unavailable)
                s.imported_preview = None
            except ValueError as exc: st.error(str(exc))
        if st.button('Discard imported proposal'):
            s.imported_preview = None
            st.info('Proposal discarded.')
    if s.get('imported_approved'):
        st.success('Imported quotation proposal approved for manifest export. No shipment booked.')
        st.download_button('Export approved imported manifest', imported_manifest(s.imported_approved).to_csv(index=False), 'approved_imported_manifest.csv', 'text/csv')

st.subheader('Focused courier versus vehicle readiness')
st.caption('USER-SUPPLIED quotes only · EasyParcel parcel couriers and Lalamove dedicated multi-stop vehicles · no booking')
from focused_quotes import template as focused_template, import_provider, evaluate as evaluate_focused, preview as preview_focused, approve as approve_focused, fingerprint as focused_fingerprint
from carrier_adapters import FocusedProviderAdapter
focused_quotes={}
for provider in ('EasyParcel Malaysia','Lalamove Malaysia'):
    st.write(f"{provider} API: {FocusedProviderAdapter(provider).fetch_rates({})['status']}")
    st.download_button(f'Download {provider} CSV template',focused_template(provider),provider.lower().replace(' ','_')+'_quotes.csv','text/csv')
    upload=st.file_uploader(f'Upload {provider} quotes',type='csv',key='focused_'+provider)
    if upload is not None:
        try: focused_quotes[provider]=import_provider(provider,upload.getvalue())
        except ValueError as exc: st.error(str(exc))
if 'imported_orders' in s and focused_quotes:
    courier=focused_quotes.get('EasyParcel Malaysia',[])
    vehicle=focused_quotes.get('Lalamove Malaysia',[])
    data=s.imported_orders
    comparison=evaluate_focused(data,courier,vehicle)
    if s.get('focused_approved') and s.get('focused_approved_fingerprint')!=focused_fingerprint(data,courier,vehicle):
        s.focused_approved=None
        st.warning('Approved comparison cleared because inputs changed.')
    st.dataframe(pd.DataFrame(comparison['reviews']))
    st.write('Readiness:',comparison['status'])
    if comparison['status']=='COMPARABLE':
        st.metric('Couriers · complete MYR',str(comparison['courier_total_myr']))
        st.metric('Dedicated vehicle · complete MYR',str(comparison['vehicle_total_myr']))
        if st.button('Preview focused comparison'):
            s.focused_preview=preview_focused(data,courier,vehicle)
            s.focused_approved=None
        if s.get('focused_preview'):
            if s.focused_preview['fingerprint']!=focused_fingerprint(data,courier,vehicle):
                s.focused_preview=None; s.focused_approved=None
                st.warning('Inputs changed; preview again.')
            else:
                st.info('Preview only · approve before using this comparison.')
                if st.button('Apply focused comparison'):
                    try:
                        s.focused_approved=approve_focused(s.focused_preview,data,courier,vehicle)
                        s.focused_approved_fingerprint=focused_fingerprint(data,courier,vehicle)
                        s.focused_preview=None
                    except ValueError as exc: st.error(str(exc))
                if st.button('Discard focused comparison'): s.focused_preview=None
        if s.get('focused_approved'):
            st.success('Comparison approved for review only. No shipment booked.')
    else:
        s.focused_preview=None; s.focused_approved=None
        st.info('NOT READY: each order needs one complete courier quote and one full vehicle quote covering the same batch and explicit stops.')

st.subheader('Mixed-method quote optimization')
st.caption('Deterministic exact cover from complete USER_IMPORTED_UNVERIFIED or LIVE_AUTHENTICATED quotes only. No booking.')
from mixed_method import optimize as optimize_mixed, preview as preview_mixed, approve as approve_mixed
if 'imported_orders' in s and focused_quotes:
    mixed_orders=s.imported_orders
    mixed_quotes=focused_quotes.get('EasyParcel Malaysia',[])+focused_quotes.get('Lalamove Malaysia',[])
    mixed_unavailable=st.multiselect('Unavailable mixed-method providers',['EasyParcel Malaysia','Lalamove Malaysia'],key='mixed_unavailable')
    try:
        mixed=optimize_mixed(mixed_orders,mixed_quotes,mixed_unavailable)
        st.write('Plan readiness:',mixed['status'])
        st.write(mixed['reason'])
        st.dataframe(pd.DataFrame(mixed['reviewed']))
        if mixed['status']=='READY':
            st.metric('Mixed quoted total MYR',str(mixed['total_myr']))
            st.metric('Eligible standalone baseline MYR',str(mixed['baseline_myr']) if mixed['baseline_myr'] is not None else 'NOT AVAILABLE')
            st.dataframe(pd.DataFrame(mixed['decisions']))
            st.warning('Manual quotations remain USER_IMPORTED_UNVERIFIED; differences are not authenticated savings.')
            if st.button('Preview mixed-method plan'):
                s.mixed_preview=preview_mixed(mixed_orders,mixed_quotes,mixed_unavailable)
                s.mixed_approved=None
            if s.get('mixed_preview'):
                from focused_quotes import fingerprint as mixed_fingerprint
                if s.mixed_preview['fingerprint']!=mixed_fingerprint(mixed_orders,mixed_quotes,[])+repr(sorted(mixed_unavailable))+repr(False):
                    s.mixed_preview=None; s.mixed_approved=None
                    st.warning('Inputs changed; generate a fresh mixed-method preview.')
                else:
                    st.info('Preview only. Approve to apply the proposed decision.')
                    if st.button('Approve mixed-method plan'):
                        try:
                            s.mixed_approved=approve_mixed(s.mixed_preview,mixed_orders,mixed_quotes,mixed_unavailable)
                            s.mixed_approved_fingerprint=s.mixed_preview['fingerprint']
                            s.mixed_preview=None
                        except ValueError as exc: st.error(str(exc))
                    if st.button('Discard mixed-method plan'): s.mixed_preview=None
            if s.get('mixed_approved'):
                if s.mixed_approved_fingerprint!=__import__('focused_quotes').fingerprint(mixed_orders,mixed_quotes,[])+repr(sorted(mixed_unavailable))+repr(False):
                    s.mixed_approved=None
                    st.warning('Approved plan cleared because inputs changed.')
                else: st.success('Mixed-method proposal approved. No transport booked.')
        else:
            s.mixed_preview=None; s.mixed_approved=None
    except ValueError as exc:
        s.mixed_preview=None; s.mixed_approved=None
        st.error(str(exc))

st.subheader('Competition demo · mixed methods')
from demo_scenario import LABEL as DEMO_LABEL, load_demo
from mixed_method import optimize as demo_optimize, preview as demo_preview, approve as demo_approve
st.error(DEMO_LABEL)
if st.button('Load Demo Scenario'):
    s.demo_orders,s.demo_quotes=load_demo()
    s.demo_unavailable=[]
    s.demo_preview=None
    s.demo_approved=None
if s.get('demo_orders') is not None:
    st.write('Four fictional shipments from one KL pickup to distinct Malaysian postcodes.')
    st.dataframe(s.demo_orders)
    unavailable=st.checkbox('Simulate disruption: vehicle provider unavailable',key='demo_disruption')
    demo_disabled=['Synthetic Lalamove example'] if unavailable else []
    if demo_disabled!=s.get('demo_unavailable'):
        s.demo_unavailable=demo_disabled
        s.demo_preview=None
        s.demo_approved=None
    plan=demo_optimize(s.demo_orders,s.demo_quotes,demo_disabled,demo=True)
    left,right=st.columns(2)
    left.metric('All-courier synthetic baseline',f"RM {plan['baseline_myr']:.2f}" if plan['baseline_myr'] is not None else 'NOT AVAILABLE')
    right.metric('Mixed synthetic plan',f"RM {plan['total_myr']:.2f}" if plan['total_myr'] is not None else 'NOT READY')
    st.write('Solver status:',plan['status'],plan['reason'])
    st.dataframe(pd.DataFrame(plan.get('decisions',[])))
    st.caption('Selected quote IDs, covered shipments, explicit stops, source and costs are fictional. No booking or payment.')
    if st.button('Preview demo plan'):
        s.demo_preview=demo_preview(s.demo_orders,s.demo_quotes,demo_disabled,demo=True)
        s.demo_approved=None
    if s.get('demo_preview'):
        st.info('PROPOSAL ONLY — review before approval. No shipment has been booked.')
        if st.button('Approve demo proposal'):
            try:
                s.demo_approved=demo_approve(s.demo_preview,s.demo_orders,s.demo_quotes,demo_disabled,demo=True)
                s.demo_preview=None
            except ValueError as exc: st.error(str(exc))
        if st.button('Discard demo proposal'): s.demo_preview=None
    if s.get('demo_approved'):
        st.success('Synthetic plan approved for demonstration. No carrier booking or payment.')
st.header('What do you need delivered?')
st.caption('Demo operations jobs are scoped to this browser session and stored on disposable local disk. Use fictional data only; this is not a private customer workspace.')
from delivery_operations import JobStore, checklist as intake_checklist
from pathlib import Path
from demo_storage import demo_job_path
ops_store=JobStore(demo_job_path(s))
from conversation_intake import extract as extract_intake, followups as intake_followups, validate_draft
st.subheader('Tell KargoKawan what you need delivered')
st.caption('Deterministic guided intake: only labeled facts are extracted. The AI provider is optional; no missing customer details are guessed.')
ops_request=st.text_area('Describe your logistics goal',placeholder='Order SME001: from Kuala Lumpur 50000 to Kuching 93000, 2 kg, 30x20x10 cm, within 7 days, recipient Customer A; budget RM50')
if st.button('Extract explicit order details'):
    draft=extract_intake(ops_request)
    s.ops_request_notes=draft['notes']
    s.ops_requested_budget=draft['budget_myr']
    if not draft['orders'].empty:
        s.ops_sample=draft['orders']
        s.ops_editor_revision=s.get('ops_editor_revision',0)+1
if s.get('ops_request_notes'):
    for note in s.ops_request_notes: st.info(note)
if s.get('ops_requested_budget'):
    st.write('User-stated budget (MYR):',s.ops_requested_budget,'· Check quote totals before approval.')
st.caption('Use the AI Logistics Assistant above for optional request interpretation. Enter actual orders and quotes below; descriptions alone never create customer data.')
if st.button('Load synthetic nationwide intake sample'):
    s.ops_sample=sample_orders().assign(recipient=lambda frame:frame.order_id.map(lambda oid:'SYNTHETIC RECIPIENT '+oid),origin_postcode='',destination_postcode='')
    st.warning('SYNTHETIC INTAKE SAMPLE — NOT CUSTOMER DATA. Exact postcodes must be supplied; city names do not determine them.')
from sample_intake import load_sample_intake
ops_upload=st.file_uploader('Import delivery operations CSV',type='csv',key='ops_csv_upload')
if ops_upload is not None:
    digest=hashlib.sha256(ops_upload.getvalue()).hexdigest()
    if digest!=s.get('ops_upload_hash'):
        try:
            s.ops_sample=load_sample_intake(ops_upload.getvalue())
            s.ops_upload_hash=digest
            s.ops_editor_revision=s.get('ops_editor_revision',0)+1
        except (ValueError,UnicodeError) as exc: st.error(f'Operations import rejected; existing orders retained: {exc}')
else: s.ops_upload_hash=None
ops_orders=st.data_editor(s.get('ops_sample',pd.DataFrame(columns=['order_id','recipient','origin_postcode','destination_postcode','weight_kg','length_cm','width_cm','height_cm','deadline_days'])),key=f'ops_orders_editor_{s.get("ops_editor_revision",0)}',num_rows='dynamic')
missing_ops=intake_checklist(ops_orders.to_dict('records'))
if missing_ops:
    st.write('User action checklist')
    for item in missing_ops[:20]: st.write('• '+item)
guided_questions=intake_followups(ops_orders)
if guided_questions:
    st.write('Focused follow-up questions')
    for question in guided_questions[:20]: st.write('• '+question)
else:
    st.success('Planning intake complete. Next: collect complete EasyParcel courier and Lalamove route quotations, including taxes, validity and restrictions. Booking requires separate approval and external confirmation.')
if st.button('Confirm corrected draft and create job'):
    try:
        valid=validate_draft(ops_orders)
        s.ops_job_id=ops_store.create(valid)
        st.success('Confirmed intake saved as job '+s.ops_job_id+'. Planning can begin after quote evidence is supplied; no booking was made.')
    except ValueError as exc: st.error(str(exc))
if st.button('Create delivery job'):
    if ops_orders.empty: st.error('Enter at least one order first.')
    else:
        s.ops_job_id=ops_store.create(ops_orders)
        st.info('Created job '+s.ops_job_id)
if s.get('mixed_approved') and 'mixed_quotes' in locals():
    if st.button('Create delivery job from approved quote plan'):
        try:
            if missing_ops: raise ValueError('Complete the recipient and postcode checklist first.')
            if set(ops_orders.order_id.astype(str)) != set(mixed_orders.order_id.astype(str)):
                raise ValueError('Job orders must match the approved quote plan exactly.')
            from focused_quotes import fingerprint as _handoff_fingerprint
            expected=_handoff_fingerprint(mixed_orders,mixed_quotes,[])+repr(sorted(mixed_unavailable))+repr(False)
            if s.get('mixed_approved_fingerprint')!=expected:
                raise ValueError('Approved plan is stale; preview and approve again.')
            s.ops_job_id=ops_store.create(ops_orders)
            ops_store.propose(s.ops_job_id,ops_orders,mixed_quotes,mixed_unavailable)
            st.info('Delivery job created for review. Approve this job separately before preparation.')
            st.rerun()
        except ValueError as exc: st.error(str(exc))
if s.get('ops_job_id'):
    job=ops_store.get(s.ops_job_id)
    st.write('Job ID:',job['job_id'],'· State:',job['state'])
    st.write('Orders:',len(job['orders']),'· Missing information:',len(intake_checklist(job['orders'])))
    st.dataframe(pd.DataFrame(job['events']))
    st.write('Agent actions: validate intake, review quote coverage, prepare a proposal. User actions: supply missing fields, approve, book with provider, record evidence.')
    if st.button('Update job intake'):
        ops_store.set_inputs(s.ops_job_id,ops_orders,[])
        st.rerun()
    if 'mixed_quotes' in locals() and mixed_quotes and not missing_ops:
        if st.button('Propose job plan from imported quotes'):
            try:
                ops_store.propose(s.ops_job_id,ops_orders,mixed_quotes,mixed_unavailable)
                st.rerun()
            except ValueError as exc: st.error(str(exc))
        if job['state']=='READY_FOR_REVIEW' and st.button('Approve delivery job plan'):
            try:
                ops_store.approve(s.ops_job_id,ops_orders,mixed_quotes,mixed_unavailable)
                st.rerun()
            except ValueError as exc: st.error(str(exc))
    if job['state']=='APPROVED' and st.button('Mark shipment preparation complete'):
        ops_store.transition(s.ops_job_id,'PREPARED','user','Manifest and package details reviewed')
        st.rerun()
    if job['state']=='PREPARED' and st.button('Handoff for manual booking'):
        ops_store.transition(s.ops_job_id,'AWAITING_BOOKING','user','Provider booking details prepared')
        st.rerun()
    if job['state']=='AWAITING_BOOKING':
        booking_reference=st.text_input('Provider booking reference')
        tracking_id=st.text_input('Tracking ID')
        booking_evidence=st.text_input('Booking confirmation evidence reference')
        if st.button('Record externally confirmed booking'):
            try:
                ops_store.record_booking(s.ops_job_id,booking_reference,tracking_id,booking_evidence)
                st.rerun()
            except ValueError as exc: st.error(str(exc))
    if job['state']=='BOOKED':
        transit_evidence=st.text_input('Carrier transit evidence')
        if st.button('Record in transit'):
            try:
                ops_store.transition(s.ops_job_id,'IN_TRANSIT','user',transit_evidence)
                st.rerun()
            except ValueError as exc: st.error(str(exc))
    if job['state']=='IN_TRANSIT':
        delivery_evidence=st.text_input('Carrier delivery evidence')
        if st.button('Record delivered'):
            try:
                ops_store.transition(s.ops_job_id,'DELIVERED','user',delivery_evidence)
                st.rerun()
            except ValueError as exc: st.error(str(exc))
    if job['state'] in ('APPROVED','PREPARED','AWAITING_BOOKING','BOOKED','IN_TRANSIT','DELIVERED'):
        st.download_button('Download approved job manifest',ops_store.manifest(s.ops_job_id).to_csv(index=False),'delivery_job_manifest.csv','text/csv')

st.subheader('Delivery operations status')
from collections import Counter
with ops_store._db() as _ops_db:
    _counts=Counter(row[0] for row in _ops_db.execute('SELECT state FROM jobs'))
for label,state in [('Needs information','NEEDS_INFORMATION'),('Awaiting approval','READY_FOR_REVIEW'),('Awaiting booking','AWAITING_BOOKING'),('Booked','BOOKED'),('In transit','IN_TRANSIT'),('Delivered','DELIVERED'),('Needs attention','NEEDS_ATTENTION')]:
    st.write(f'{label}: {_counts[state]}')

st.header('Collect real shipping quotations')
st.caption('EasyParcel rate lookup is optional; manual evidence remains available. Lalamove live quotations are not enabled.')
from carrier_adapters import EasyParcelAdapter, EasyParcelOpenApiAdapter, LalamoveAdapter
_easy_adapter=EasyParcelAdapter()
_lama_adapter=LalamoveAdapter()
st.write('EasyParcel Individual API key:',
         'CREDENTIALS PRESENT — response not verified' if _easy_adapter.connection_status()=='CONNECTED' else 'NOT_CONNECTED',
         '· Lalamove connection:',_lama_adapter.connection_status())
st.caption('EasyParcel Open API OAuth: '+EasyParcelOpenApiAdapter().connection_status()+' · Account linking is disabled until users and delivery jobs have private, authenticated access.')
from quote_guidance import request_checklist, request_details, vehicle_candidates, make_draft, collection_progress
from mixed_method import preview as guided_preview, approve as guided_approve
from focused_quotes import fingerprint as guided_fingerprint
import json as _guided_json
if s.get('ops_job_id'):
    guided_job=ops_store.get(s.ops_job_id)
    if not intake_checklist(guided_job['orders']):
        st.subheader('Quote request preparation')
        st.dataframe(pd.DataFrame(request_details(guided_job['orders'])))
        st.download_button('Download minimal quote request CSV',pd.DataFrame(request_details(guided_job['orders'])).to_csv(index=False),'quote_request_details.csv','text/csv')
        for task in request_checklist(guided_job['orders']): st.write('• '+task)
        for candidate in vehicle_candidates(guided_job['orders']):
            st.info('Possible Lalamove quote request, not confirmed service: '+', '.join(candidate['shipment_ids']))
            st.json(candidate['stops'])
    else: st.info('Complete the job intake checklist before requesting route quotes.')
else: st.info('Create a delivery job first; the quote request uses its confirmed shipment details.')
from quote_guidance import order_facts, malaysia_timestamp, missing_quote_actions
from datetime import datetime as _dt, date as _date, time as _time
from zoneinfo import ZoneInfo as _ZoneInfo
selected_job=None
all_jobs=[item for item in ops_store.list_jobs() if item['state'] not in ('BOOKED','IN_TRANSIT','DELIVERED','CANCELLED','FAILED')]
job_labels={f"{item['job_id']} · {item['state']}":item['job_id'] for item in all_jobs}
if not job_labels:
    st.info('Create a delivery job first. Its orders will fill the quotation form.')
else:
    selected_job_label=st.selectbox('Select delivery job',list(job_labels))
    selected_job=ops_store.get(job_labels[selected_job_label])
    selected_rows=selected_job['orders']
    st.caption('Order facts below come from this job. Provider eligibility, service, price and expiry still need quotation evidence.')
    entry_provider=st.selectbox('Choose quotation provider',['EasyParcel Malaysia','Lalamove Malaysia'])
    if entry_provider=='EasyParcel Malaysia':
        selected_ids=[st.selectbox('Choose one delivery order',[str(row['order_id']) for row in selected_rows])]
    else:
        candidates=vehicle_candidates(selected_rows)
        if candidates:
            chosen_candidate=st.selectbox('Choose a possible same-region route to request',range(len(candidates)),format_func=lambda i:', '.join(candidates[i]['shipment_ids']))
            selected_ids=st.multiselect('Choose orders covered by the vehicle quote',candidates[chosen_candidate]['shipment_ids'],default=candidates[chosen_candidate]['shipment_ids'])
            st.warning('Possible request only. Provider route coverage and stop sequence must be confirmed by its quote.')
        else:
            selected_ids=[]
            st.warning('No same-region vehicle request candidate is available for this job. This does not establish carrier coverage elsewhere.')
    selected_facts=None
    if selected_ids:
        try:
            selected_facts=order_facts(selected_rows,selected_ids)
            st.dataframe(pd.DataFrame([row for row in selected_rows if str(row['order_id']) in selected_ids])[['order_id','origin_postcode','destination_postcode','weight_kg','length_cm','width_cm','height_cm','deadline_days']])
        except ValueError as exc: st.error(str(exc))
    if entry_provider=='EasyParcel Malaysia' and selected_facts:
        st.caption('Authenticated rate check only. Returned display prices are INCOMPLETE until full payable cost, taxes, surcharges and expiry are confirmed.')
        api_origin_state=st.text_input('Origin Malaysian state for provider lookup',key='api_origin_state')
        api_destination_state=st.text_input('Destination Malaysian state for provider lookup',key='api_destination_state')
        if st.button('Fetch available quotations'):
            row=next(row for row in selected_rows if str(row['order_id'])==selected_ids[0])
            request_facts={'order_id':str(row['order_id']),'origin_postcode':str(row['origin_postcode']),
                'destination_postcode':str(row['destination_postcode']),'origin_state':api_origin_state,
                'destination_state':api_destination_state,'weight_kg':row['weight_kg'],
                'length_cm':row['length_cm'],'width_cm':row['width_cm'],'height_cm':row['height_cm']}
            s.provider_rate_result=_easy_adapter.fetch_rates(request_facts)
            s.provider_rate_order=(selected_job['job_id'],selected_ids[0])
        if s.get('provider_rate_result') and s.get('provider_rate_order')==(selected_job['job_id'],selected_ids[0]):
            st.write('Provider lookup:',s.provider_rate_result['status'],s.provider_rate_result['reason'])
            if s.provider_rate_result['quotes']:
                st.dataframe(pd.DataFrame(s.provider_rate_result['quotes']))
                st.warning('INCOMPLETE display rates are research observations, not eligible plan quotations. Review the payable amount and validity through the manual evidence form.')
    if selected_facts:
        with st.form('manual_quote_entry'):
            st.subheader('Enter quotation details')
            entry_id=st.text_input('Provider quote ID or your evidence ID')
            entry_service=st.text_input('Service shown on the quotation')
            entry_pickup=st.text_input('Pickup location or reference shown on quote')
            if entry_provider=='Lalamove Malaysia':
                st.write('Edit the exact stop sequence and postcodes shown on the provider quote:')
                stop_table=st.data_editor(pd.DataFrame(selected_facts['stops']),hide_index=True,num_rows='fixed',key=f'guided_stop_editor_{selected_job["job_id"]}_{"_".join(selected_ids)}')
                route_confirmed=st.checkbox('Provider confirmed this exact vehicle route and stop order')
                entry_capacity=st.text_input('Provider-confirmed vehicle capacity (kg)')
            else:
                stop_table=None
                route_confirmed=False
                entry_capacity=''
            st.subheader('Confirm full payable price and charges')
            st.caption('Package facts are prefilled from the job. Confirm that the provider accepts these dimensions before they count as quoted limits.')
            dimensions_confirmed=st.checkbox('Provider confirmed the displayed package dimensions are accepted')
            st.write(f"Order weight: {selected_facts['physical_weight_kg']} kg · Largest package: {selected_facts['max_order_length_cm']} × {selected_facts['max_order_width_cm']} × {selected_facts['max_order_height_cm']} cm")
            entry_price=st.text_input('Full payable price in MYR')
            entry_full=st.checkbox('This is the complete payable amount')
            entry_tax=st.selectbox('Does the total include applicable tax?',['UNKNOWN','included','excluded'])
            entry_surcharge=st.selectbox('Does the total include all applicable surcharges?',['UNKNOWN','included','excluded'])
            st.subheader('Add evidence and review')
            malaysia_now=_dt.now(_ZoneInfo('Asia/Kuala_Lumpur'))
            collected_day=st.date_input('Quotation collected date (Malaysia time)',value=malaysia_now.date())
            collected_clock=st.time_input('Quotation collected time (Malaysia time)',value=malaysia_now.time().replace(second=0,microsecond=0))
            expiry_day=st.date_input('Quote expiry date (Malaysia time)',value=None)
            expiry_clock=st.time_input('Quote expiry time (Malaysia time)',value=_time(23,59)) if expiry_day else None
            entry_transit=st.text_input('Estimated transit days')
            entry_restrictions=st.text_input('Provider conditions or restrictions (enter none only if confirmed)')
            entry_evidence=st.text_input('Provider evidence reference or saved document')
            review_entry=st.form_submit_button('Review quote draft')
        if review_entry:
            try:
                if not entry_service.strip() or not entry_evidence.strip():
                    raise ValueError('Add the quoted service and provider evidence reference before review.')
                if entry_provider=='Lalamove Malaysia' and len(selected_ids)<2:
                    raise ValueError('Select at least two orders for a multi-stop vehicle quote.')
                stops=stop_table.to_dict('records') if entry_provider=='Lalamove Malaysia' and route_confirmed else []
                fields={'quote_id':entry_id,'provider':entry_provider,'service':entry_service,
                        'transport_method':'parcel_courier' if entry_provider=='EasyParcel Malaysia' else 'multi_stop_vehicle',
                        'origin_postcode':selected_facts['origin_postcode'],'destination_postcode':selected_facts['destination_postcode'],
                        'pickup_location':entry_pickup,'dropoff_locations':stops,'shipment_ids':selected_facts['shipment_ids'],
                        'physical_weight_kg':str(selected_facts['physical_weight_kg']),'capacity_kg':entry_capacity,
                        'length_cm':str(selected_facts['max_order_length_cm']) if dimensions_confirmed else '',
                        'width_cm':str(selected_facts['max_order_width_cm']) if dimensions_confirmed else '',
                        'height_cm':str(selected_facts['max_order_height_cm']) if dimensions_confirmed else '',
                        'displayed_cost_myr':entry_price,'full_cost':'true' if entry_full else 'false',
                        'tax_status':entry_tax,'surcharge_status':entry_surcharge,
                        'collected_at':malaysia_timestamp(collected_day,collected_clock).isoformat(),
                        'valid_until':malaysia_timestamp(expiry_day,expiry_clock).isoformat() if expiry_day else '',
                        'transit_days':entry_transit,'restrictions':entry_restrictions,'source_reference':entry_evidence}
                s.guided_draft=make_draft(fields)
                s.guided_draft_job_id=selected_job['job_id']
            except (ValueError,TypeError) as exc: st.error(str(exc))
if s.get('guided_draft') and selected_job and s.get('guided_draft_job_id')==selected_job['job_id']:
    st.caption('Draft for delivery job '+selected_job['job_id'])
    from hybrid_quotes import review as review_guided_quote
    guided_orders=ops_store.get(s.guided_draft_job_id)['orders'] if s.get('guided_draft_job_id') else []
    draft_review=review_guided_quote(s.guided_draft,guided_orders)
    st.write('Draft review:',draft_review['status'],draft_review['reason'])
    for action in missing_quote_actions(s.guided_draft,guided_orders): st.write('• '+action)
    st.caption('To correct the draft, edit the form and select Review quote draft again.')
    if st.button('Save reviewed manual quote'):
        s.setdefault('guided_quotes_by_job',{}).setdefault(s.guided_draft_job_id,[]).append(s.guided_draft)
        s.guided_proposal=None
        s.guided_approved=None
        s.guided_draft=None
if selected_job and s.get('guided_quotes_by_job',{}).get(selected_job['job_id']):
    guided_orders_frame=pd.DataFrame(selected_job['orders'])
    guided_all=s.guided_quotes_by_job[selected_job['job_id']]+focused_quotes.get('EasyParcel Malaysia',[])+focused_quotes.get('Lalamove Malaysia',[])
    try:
        progress=collection_progress(guided_orders_frame,guided_all)
        st.subheader('Quotation progress')
        st.dataframe(pd.DataFrame([{'Order ID':oid,'Eligible courier quote IDs':', '.join(ids) or 'NONE'} for oid,ids in progress['courier_by_order'].items()]))
        st.dataframe(pd.DataFrame(progress['reviews']))
        st.write('Vehicle route subsets:',progress['vehicle_subsets'])
        for action in progress['next_actions']: st.write('Next action: '+action)
        st.write('Planning status:',progress['plan']['status'])
        if progress['plan']['status'] in ('READY','SOLVER LIMITED'):
            st.metric('Quoted mixed plan (MYR)',str(progress['plan']['total_myr']))
            st.write('Selected quote evidence:')
            st.dataframe(pd.DataFrame(progress['plan']['decisions']))
            if st.button('Preview guided quote plan'):
                s.guided_proposal=guided_preview(guided_orders_frame,guided_all)
                s.guided_approved=None
            if s.get('guided_proposal'):
                if s.guided_proposal['fingerprint']!=guided_fingerprint(guided_orders_frame,guided_all,[])+repr([])+repr(False):
                    s.guided_proposal=None; s.guided_approved=None
                    st.warning('Quote or order inputs changed. Preview again.')
                else:
                    st.info('Plan proposal only. No booking or payment.')
                    if st.button('Approve guided quote plan'):
                        s.guided_approved=guided_approve(s.guided_proposal,guided_orders_frame,guided_all)
                        s.guided_approved_fingerprint=guided_fingerprint(guided_orders_frame,guided_all,[])+repr([])+repr(False)
                        s.guided_proposal=None
                    if st.button('Discard guided quote plan'): s.guided_proposal=None
            if s.get('guided_approved') and selected_job:
                if s.get('guided_approved_fingerprint')!=guided_fingerprint(guided_orders_frame,guided_all,[])+repr([])+repr(False):
                    s.guided_approved=None
                    st.warning('Approved quote plan is stale; review and approve again.')
                elif st.button('Send approved plan to delivery job for separate review'):
                    try:
                        ops_store.propose(selected_job['job_id'],guided_orders_frame,guided_all)
                        st.success('Job proposal created. Approve the delivery job separately before preparation.')
                    except ValueError as exc: st.error(str(exc))
    except ValueError as exc: st.error(str(exc))
