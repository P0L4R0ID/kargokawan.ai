"""Five-order fictional logistics walkthrough; session-only, never pilot evidence."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import streamlit as st

from hybrid_quotes import normalize
from mixed_method import optimize, preview, approve
from sample_intake import validate_complete

LABEL = 'FICTIONAL DEMONSTRATION — NOT REAL CARRIER PRICES, QUOTES OR BOOKINGS'
VAN = 'Fictional Metro Multi-stop Van'
COURIER = 'Fictional Nationwide Parcel Courier'

# Three explicit Klang Valley road stops, then two separate intercity parcels.
SHIPMENTS = (
    ('FEST001', 'Kuala Lumpur', '50000', 'Kuala Lumpur', '50100', Decimal('1.0'), 1, 'FICTIONAL RECIPIENT A'),
    ('FEST002', 'Kuala Lumpur', '50000', 'Kuala Lumpur', '50450', Decimal('2.0'), 2, 'FICTIONAL RECIPIENT B'),
    ('FEST003', 'Kuala Lumpur', '50000', 'Kuala Lumpur', '51000', Decimal('1.5'), 2, 'FICTIONAL RECIPIENT C'),
    ('FEST004', 'Kuala Lumpur', '50000', 'George Town', '10000', Decimal('3.0'), 4, 'FICTIONAL RECIPIENT D'),
    ('FEST005', 'Kuala Lumpur', '50000', 'Johor Bahru', '80000', Decimal('2.0'), 3, 'FICTIONAL RECIPIENT E'),
)


def load_scenario():
    """Return internally consistent synthetic orders and quoted alternatives."""
    orders = pd.DataFrame([{
        'order_id': oid, 'origin': origin, 'destination': destination,
        'weight_kg': float(weight), 'length_cm': 25, 'width_cm': 20,
        'height_cm': 15, 'deadline_days': deadline, 'recipient': recipient,
        'origin_postcode': origin_postcode, 'destination_postcode': destination_postcode,
    } for oid, origin, origin_postcode, destination, destination_postcode, weight, deadline, recipient in SHIPMENTS])
    orders = validate_orders(orders)
    now = datetime.now(timezone.utc)
    common = {'source_class': 'SYNTHETIC', 'origin_postcode': '50000',
              'pickup_location': 'Fictional Kuala Lumpur SME pickup',
              'length_cm': '30', 'width_cm': '25', 'height_cm': '20',
              'full_cost': 'true', 'tax_status': 'included', 'surcharge_status': 'included',
              'source_reference': LABEL + ' · internal cost assumption',
              'collected_at': now.isoformat(), 'valid_until': (now + timedelta(days=1)).isoformat(),
              'restrictions': 'none'}
    quotes = []
    costs = {'FEST001': '18.00', 'FEST002': '22.00', 'FEST003': '24.00',
             'FEST004': '36.00', 'FEST005': '32.00'}
    for row in orders.to_dict('records'):
        oid = row['order_id']
        transit = {'FEST001': 1, 'FEST002': 2, 'FEST003': 2,
                   'FEST004': 3, 'FEST005': 2}[oid]
        quotes.append(normalize({**common, 'quote_id': 'FICTIONAL-PARCEL-' + oid,
            'provider': COURIER, 'service': 'Fictional standalone parcel',
            'transport_method': 'parcel_courier', 'destination_postcode': row['destination_postcode'],
            'dropoff_locations': '', 'shipment_ids': oid, 'physical_weight_kg': str(row['weight_kg']),
            'capacity_kg': '5', 'displayed_cost_myr': costs[oid], 'transit_days': str(transit)}))
    stops = [{'shipment_id': row['order_id'], 'postcode': row['destination_postcode'], 'sequence': i + 1}
             for i, row in enumerate(orders.to_dict('records')[:3])]
    quotes.append(normalize({**common, 'quote_id': 'FICTIONAL-VAN-KV-3',
        'provider': VAN, 'service': 'Fictional three-stop road vehicle',
        'transport_method': 'multi_stop_vehicle', 'destination_postcode': stops[0]['postcode'],
        'dropoff_locations': json.dumps(stops), 'shipment_ids': ';'.join(stop['shipment_id'] for stop in stops),
        'physical_weight_kg': '4.5', 'capacity_kg': '8',
        'displayed_cost_myr': '45.00', 'transit_days': '1'}))
    # Attractive-looking alternatives that miss their explicit deadlines.
    for oid, cost, transit in (('FEST002', '15.00', 3), ('FEST004', '28.00', 5)):
        row = orders.set_index('order_id').loc[oid]
        quotes.append(normalize({**common, 'quote_id': 'FICTIONAL-SLOW-' + oid,
            'provider': COURIER, 'service': 'Fictional slow parcel alternative',
            'transport_method': 'parcel_courier', 'destination_postcode': row['destination_postcode'],
            'dropoff_locations': '', 'shipment_ids': oid, 'physical_weight_kg': str(row['weight_kg']),
            'capacity_kg': '5', 'displayed_cost_myr': cost, 'transit_days': str(transit)}))
    return orders, quotes


def validate_orders(orders):
    """Reuse the established CSV intake checks, preserving postcode strings."""
    frame = orders.copy() if isinstance(orders, pd.DataFrame) else pd.DataFrame(orders)
    return validate_complete(frame.to_csv(index=False))


def alternatives(orders, quotes, unavailable=()):
    result = optimize(orders, quotes, unavailable, demo=True)
    reviewed = {item['quote_id']: item for item in result['reviewed']}
    deadline = {str(row['order_id']): int(row['deadline_days']) for row in orders.to_dict('records')}
    return pd.DataFrame([{
        'Assumed quote': quote['quote_id'], 'Fictional provider': quote['provider'],
        'Service': quote['service'], 'Method': quote['transport_method'],
        'Orders covered': ', '.join(quote['shipment_ids']),
        'Ordered stops': ', '.join(f"{stop['sequence']}: {stop['shipment_id']} {stop['postcode']}"
                                   for stop in quote['dropoff_locations']) or 'Single parcel',
        'Assumed MYR total': str(quote['displayed_cost_myr']),
        'Assumed transit days': quote['transit_days'],
        'Order deadlines (days)': ', '.join(f'{oid}: {deadline[oid]}' for oid in quote['shipment_ids']),
        'Review': reviewed[quote['quote_id']]['status'],
        'Reason': reviewed[quote['quote_id']]['reason'],
        'Source': quote['source_reference'],
    } for quote in quotes])


def manifest(orders, approved):
    """Produce a preparation list only after explicit demo approval."""
    if approved is None or approved.get('status') not in ('READY', 'SOLVER LIMITED'):
        raise ValueError('Approve a fictional proposal before exporting its manifest.')
    if not approved.get('claim', '').startswith('SIMULATED DEMO'):
        raise ValueError('Only a fictional approved result belongs in this manifest.')
    decisions = approved['decisions']
    rows = []
    for order in orders.to_dict('records'):
        matches = [item for item in decisions if order['order_id'] in item['shipment_ids']]
        if len(matches) != 1 or matches[0]['source_class'] != 'SYNTHETIC':
            raise ValueError('Fictional plan must cover each order exactly once.')
        choice = matches[0]
        rows.append({'Status': 'FICTIONAL PREPARATION ONLY — NOT A BOOKING',
            'Order ID': order['order_id'], 'Fictional recipient': order['recipient'],
            'Origin postcode': order['origin_postcode'],
            'Destination postcode': order['destination_postcode'],
            'Deadline (days)': order['deadline_days'], 'Fictional provider': choice['provider'],
            'Service': choice['service'], 'Method': choice['method'],
            'Assumed quote ID': choice['quote_id'],
            'Assumed group total MYR': str(choice['total_myr']),
            'Assumption source': choice['source_reference']})
    return pd.DataFrame(rows)


def approve_scenario(proposal, orders, quotes, unavailable=()):
    """Keep approval tied to the previewed fictional recommendation."""
    current = approve(proposal, orders, quotes, unavailable, demo=True)
    previous = proposal['result']
    if (current['status'] != previous['status'] or
            current['total_myr'] != previous['total_myr'] or
            [item['quote_id'] for item in current['selected']] !=
            [item['quote_id'] for item in previous['selected']]):
        raise ValueError('Fictional recommendation changed; preview again before approval.')
    return current


def assistant_brief(result=None, *, loaded=False, validated=False, previewed=False,
                    approved=False, prepared=False, last_change=None, previous=None):
    """Explain the current fictional workflow from checked state, never from a claim flag."""
    if not loaded:
        return {'stage': 'Start', 'next': 'Load the five fictional deliveries.',
                'message': 'I can check five example deliveries and compare the available test options.'}
    if not validated:
        return {'stage': 'Blocked', 'next': 'Correct the order details and validate again.',
                'message': 'I cannot recommend a plan until the delivery details pass validation.'}
    if result is None:
        return {'stage': 'Orders checked', 'next': 'Review the delivery options.',
                'message': 'The delivery details are complete. I still need to check the available options.'}
    if result['status'] == 'NOT READY':
        detail = result['reason']
        return {'stage': 'Blocked', 'next': 'Adjust a deadline or restore a provider, then review again.',
                'message': 'I cannot find an eligible option for every delivery. ' + detail}
    decisions = result['decisions']
    groups = '; '.join(f"{item['service']} for {', '.join(item['shipment_ids'])} (RM {item['total_myr']:.2f})"
                       for item in decisions)
    proven = result['status'] == 'READY'
    message = ('I checked your five deliveries. ' if len({oid for item in decisions for oid in item['shipment_ids']}) == 5 else
               'I checked the deliveries. ')
    message += ('Here is the cheapest eligible option under these test assumptions: ' if proven else
                'Here is a feasible option; the solver did not prove it is cheapest: ') + groups + '.'
    if result['baseline_myr'] is not None:
        message += f" The eligible all-parcel baseline is RM {result['baseline_myr']:.2f}; the difference is RM {result['difference_myr']:.2f}."
    else:
        message += ' There is no complete eligible all-parcel baseline to compare.'
    if last_change:
        if previous and previous.get('total_myr') is not None:
            delta = result['total_myr'] - previous['total_myr']
            message += f" The earlier feasible plan was RM {previous['total_myr']:.2f}; this one is RM {result['total_myr']:.2f} ({delta:+.2f} MYR)."
        message += ' The earlier approval was cleared; this plan needs a fresh review.'
    if prepared:
        return {'stage': 'Preparation started', 'next': 'Use the approved manifest for fictional preparation only.', 'message': message}
    if approved:
        return {'stage': 'Approved', 'next': 'Download the preparation manifest, then mark fictional packages prepared.', 'message': message}
    if previewed:
        return {'stage': 'Awaiting approval', 'next': 'Review the proposal, then approve or discard it.', 'message': message}
    return {'stage': 'Replan required' if last_change else 'Plan ready',
            'next': 'Preview the recommendation for a separate human approval.', 'message': message}


def _reset_plan(state, event):
    state.festival_previous_plan = state.get('festival_current_plan')
    state.festival_last_change = event
    state.festival_preview = None
    state.festival_approved = None
    state.festival_prepared = False
    state.festival_events.append(event)


def _timeline(events):
    labels = {
        'FICTIONAL INTAKE LOADED': 'Orders loaded and checked',
        'FICTIONAL PLAN PROPOSED': 'Plan suggested for review',
        'HUMAN APPROVED': 'Human approved fictional preparation',
        'FICTIONAL PACKAGES MARKED PREPARED': 'Preparation marked in this session',
        'FICTIONAL PROVIDER DISRUPTION': 'Van marked unavailable; approval reset',
        'FICTIONAL PROVIDER RESTORED': 'Van restored; approval reset',
        'FICTIONAL DEADLINE CHANGED': 'Deadline changed; approval reset',
        'FICTIONAL PROPOSAL DISCARDED': 'Proposal discarded',
    }
    for number, event in enumerate(events, 1):
        title = next((value for key, value in labels.items() if event.startswith(key)), event)
        st.write(f'**{number}. {title}**')
        if title != event:
            st.caption(event)


def _selected_groups(result):
    for choice in result.get('decisions', []):
        name = 'Shared three-stop vehicle' if choice['method'] == 'multi_stop_vehicle' else 'Standalone parcel'
        with st.container(border=True):
            st.write(f"**{name} · RM {choice['total_myr']:.2f} assumed**")
            st.write(f"{choice['service']} · {', '.join(choice['shipment_ids'])}")
            st.caption('Fictional provider: ' + choice['provider'])


def render():
    state = st.session_state
    st.subheader('Five-order delivery walkthrough')
    st.caption(LABEL + ' · Session-only; no pilot job or carrier call.')
    if state.get('festival_orders') is None:
        brief = assistant_brief()
        st.info(f"KargoKawan operations assistant · {brief['message']}")
        st.write('**Next action:** ' + brief['next'])
        if st.button('Load five-order fictional scenario', type='primary'):
            state.festival_orders, state.festival_quotes = load_scenario()
            state.festival_unavailable = []
            state.festival_preview = None
            state.festival_approved = None
            state.festival_prepared = False
            state.festival_events = ['FICTIONAL INTAKE LOADED · no booking']
            state.festival_previous_plan = None
            state.festival_current_plan = None
            state.festival_last_change = None
            st.rerun()
        return

    orders, quotes = state.festival_orders, state.festival_quotes
    try:
        validate_orders(orders)
    except ValueError as exc:
        brief = assistant_brief(loaded=True)
        st.warning(f"{brief['stage']} · {brief['message']} {exc} Next action: {brief['next']}")
        return
    unavailable = state.festival_unavailable
    result = optimize(orders, quotes, unavailable, demo=True)
    state.festival_current_plan = result
    brief = assistant_brief(result, loaded=True, validated=True,
                            previewed=bool(state.get('festival_preview')),
                            approved=bool(state.get('festival_approved')),
                            prepared=bool(state.get('festival_prepared')),
                            last_change=state.get('festival_last_change'),
                            previous=state.get('festival_previous_plan'))
    overview, order_tab, plan_tab, review_tab, activity_tab = st.tabs(
        ['Overview', 'Delivery orders', 'Plan & compare', 'Review & approve', 'Activity'])

    with overview:
        st.info(f"KargoKawan operations assistant · **{brief['stage']}** · {brief['message']}\n\nNext action: {brief['next']}")
        if result['status'] != 'NOT READY':
            if state.get('festival_preview'):
                st.caption('Open Review & approve to make the human decision.')
            elif state.get('festival_approved'):
                if not state.get('festival_prepared') and st.button('Mark fictional packages prepared', type='primary'):
                    state.festival_prepared = True
                    state.festival_events.append('FICTIONAL PACKAGES MARKED PREPARED · no dispatch')
                    st.rerun()
            elif st.button('Preview five-order fictional plan', type='primary'):
                state.festival_preview = preview(orders, quotes, unavailable, demo=True)
                state.festival_approved = None
                state.festival_prepared = False
                state.festival_events.append('FICTIONAL PLAN PROPOSED · no booking or payment')
                st.rerun()
        st.caption('Workflow: orders checked → options compared → proposal → human approval → fictional preparation. No booking or dispatch.')
        col1, col2, col3 = st.columns(3)
        col1.metric('Deliveries covered', f"{len({oid for choice in result.get('selected', []) for oid in choice['shipment_ids']})} / {len(orders)}")
        baseline = result['baseline_myr']
        col2.metric('Eligible parcel baseline', f'RM {baseline:.2f}' if baseline is not None else 'Not available')
        col3.metric('Recommended assumed cost', f"RM {result['total_myr']:.2f}" if result['total_myr'] is not None else 'NOT READY')
        if baseline is not None and result['total_myr'] is not None:
            st.caption(f"Assumed difference: RM {result['difference_myr']:.2f}, compared with eligible standalone parcels from this same fictional quote set.")
        if state.get('festival_last_change'):
            st.warning(state.festival_last_change)
            previous = state.get('festival_previous_plan')
            if previous and previous.get('total_myr') is not None and result['total_myr'] is not None:
                old_ids = {item['quote_id'] for item in previous['selected']}
                new_ids = {item['quote_id'] for item in result['selected']}
                delta = result['total_myr'] - previous['total_myr']
                st.write(f"What changed: assumed plan RM {previous['total_myr']:.2f} → RM {result['total_myr']:.2f} "
                         f"({delta:+.2f} MYR). Removed: {', '.join(sorted(old_ids-new_ids)) or 'none'}. "
                         f"Added: {', '.join(sorted(new_ids-old_ids)) or 'none'}.")
            elif previous and result['status'] == 'NOT READY':
                st.write('What changed: the previous fictional plan is no longer feasible; no replacement manifest is available.')

    with order_tab:
        st.subheader('Delivery orders')
        st.success('Orders checked: unique IDs, exact five-digit postcodes, positive parcel measurements and deadlines.')
        for row in orders.to_dict('records'):
            with st.container(border=True):
                st.write(f"**{row['order_id']} · {row['destination']} {row['destination_postcode']}**")
                st.caption(f"From {row['origin']} {row['origin_postcode']} · {row['weight_kg']} kg · "
                           f"{row['length_cm']} × {row['width_cm']} × {row['height_cm']} cm · "
                           f"Deadline {row['deadline_days']} day(s) · {row['recipient']}")
        st.write('**Adjust a fictional deadline**')
        ids = orders.order_id.astype(str).tolist()
        selected_id = st.selectbox('Fictional order to adjust deadline', ids, key='festival_deadline_order')
        current_days = int(orders.set_index('order_id').loc[selected_id, 'deadline_days'])
        new_days = st.number_input('Revised fictional deadline (days)', min_value=1, max_value=14,
                                   value=current_days, step=1, key='festival_deadline_value_' + selected_id)
        if st.button('Apply fictional deadline change'):
            changed = orders.copy()
            changed.loc[changed.order_id == selected_id, 'deadline_days'] = int(new_days)
            try:
                state.festival_orders = validate_orders(changed)
                _reset_plan(state, f'FICTIONAL DEADLINE CHANGED · {selected_id}: {current_days} → {int(new_days)} days')
                st.rerun()
            except ValueError as exc:
                st.error('Deadline change rejected: ' + str(exc))
        with st.expander('Detailed order data'):
            st.dataframe(orders, hide_index=True)

    with plan_tab:
        st.subheader('Plan & compare')
        st.write('Solver:', result['status'], '·', result['reason'])
        if result['status'] == 'NOT READY':
            uncovered = sorted(set(orders.order_id.astype(str)) - {
                oid for quote, checked in zip(quotes, result['reviewed']) if checked['status'] == 'ELIGIBLE'
                for oid in quote['shipment_ids']})
            st.warning('No complete eligible fictional plan. ' +
                       (f"No eligible quote covers {', '.join(uncovered)}. " if uncovered else '') +
                       'Adjust deadlines or restore provider availability; no manifest can be prepared.')
        else:
            st.write('**Recommended shipment groups**')
            _selected_groups(result)
            if result['baseline_myr'] is not None:
                left, right = st.columns(2)
                left.metric('All-parcel eligible baseline', f"RM {result['baseline_myr']:.2f}")
                right.metric('Mixed-method recommendation', f"RM {result['total_myr']:.2f}")
            else:
                st.caption('No complete eligible all-parcel baseline is available.')
        excluded = [item for item in result['reviewed'] if item['status'] == 'EXCLUDED']
        if excluded:
            st.write('**Options not used**')
            for item in excluded:
                st.write(f"{item['quote_id']}: {item['reason']}")
        with st.expander('Assumption evidence and all alternatives'):
            st.dataframe(alternatives(orders, quotes, unavailable), hide_index=True)
            if result.get('decisions'):
                st.dataframe(pd.DataFrame(result['decisions']), hide_index=True)

    with review_tab:
        st.subheader('Review & approve')
        if result['status'] == 'NOT READY':
            st.warning('No proposal can be approved while a delivery has no eligible option.')
        elif state.get('festival_preview'):
            st.info('Proposal only. Approval authorizes fictional preparation, not booking, payment or dispatch.')
            _selected_groups(state.festival_preview['result'])
            st.write(f"**Proposed assumed total: RM {state.festival_preview['result']['total_myr']:.2f}**")
            if st.button('Approve five-order fictional plan', type='primary'):
                try:
                    state.festival_approved = approve_scenario(state.festival_preview, orders, quotes, unavailable)
                    state.festival_preview = None
                    state.festival_prepared = False
                    state.festival_events.append('HUMAN APPROVED FICTIONAL PLAN · no booking or payment')
                    st.rerun()
                except ValueError as exc:
                    state.festival_preview = None
                    st.error('Proposal is stale or infeasible: ' + str(exc))
            if st.button('Discard five-order fictional proposal'):
                state.festival_preview = None
                state.festival_events.append('FICTIONAL PROPOSAL DISCARDED · no change to orders')
                st.rerun()
        elif state.get('festival_approved'):
            st.success('Fictional plan approved by a human. No carrier has been contacted, booked, paid or dispatched.')
            table = manifest(orders, state.festival_approved)
            st.download_button('Download fictional preparation manifest — NOT A BOOKING',
                               table.to_csv(index=False), 'fictional_five_order_manifest.csv', 'text/csv')
            st.caption('Verify real addresses, rates and service availability before any real shipment outside this demo.')
        else:
            st.info('Review the recommendation on Plan & compare, then preview it using the action on Overview. Approval is a separate step.')

    with activity_tab:
        st.subheader('Activity & disruptions')
        st.write('**Fictional decision history**')
        _timeline(state.festival_events)
        if VAN not in unavailable:
            if st.button('Simulate fictional van disruption'):
                state.festival_unavailable = [VAN]
                _reset_plan(state, 'FICTIONAL PROVIDER DISRUPTION · van unavailable; prior approval cleared')
                st.rerun()
        elif st.button('Restore fictional van'):
            state.festival_unavailable = []
            _reset_plan(state, 'FICTIONAL PROVIDER RESTORED · prior approval cleared')
            st.rerun()
        st.caption('Availability changes invalidate prior approval and require a new proposal. No carrier is contacted.')
