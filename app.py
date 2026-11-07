import io
import hashlib
import pandas as pd
import streamlit as st
from engine import sample_orders, CITIES
from dashboard import PROVIDERS, normalize, replan, manifest
from agent import run_request, approve

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
st.caption('Optional OpenAI mode sends your request and computed shipment data to OpenAI. Use anonymized orders and never include personal information. Without a key, deterministic command matching remains available.')
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
    st.write(answer['label'] + ' · ' + answer['mode'])
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
