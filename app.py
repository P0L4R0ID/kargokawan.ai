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
