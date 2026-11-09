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


def render():
    st.subheader('Festival challenge · five-order fictional walkthrough')
    st.error(LABEL)
    st.caption('A five-minute intake → decision → approval → preparation demonstration. Session-only; no pilot job or carrier API call.')
    st.markdown('#### KargoKawan operations assistant')
    state = st.session_state
    if st.button('Load five-order fictional scenario'):
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
    if state.get('festival_orders') is None:
        brief = assistant_brief()
        st.info(f"{brief['stage']} · {brief['message']} Next action: {brief['next']}")
        return
    orders, quotes = state.festival_orders, state.festival_quotes
    try:
        validate_orders(orders)
        st.success('Intake validated: five fictional orders have unique IDs, exact postcodes, positive parcel measurements and deadlines.')
    except ValueError as exc:
        brief = assistant_brief(loaded=True)
        st.warning(f"{brief['stage']} · {brief['message']} {exc} Next action: {brief['next']}")
        return
    st.dataframe(orders, hide_index=True)
    st.caption('Three explicit Klang Valley road stops can share the fictional van. Penang and Johor orders use separate fictional parcels.')
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
    if st.button('Simulate fictional van disruption'):
        if VAN not in state.festival_unavailable:
            state.festival_unavailable = [VAN]
            _reset_plan(state, 'FICTIONAL PROVIDER DISRUPTION · van unavailable; prior approval cleared')
            st.rerun()
        st.info('Van unavailable. Recalculate and approve a replacement before preparation.')
    if st.button('Restore fictional van'):
        if VAN in state.festival_unavailable:
            state.festival_unavailable = []
            _reset_plan(state, 'FICTIONAL PROVIDER RESTORED · prior approval cleared')
            st.rerun()
        st.info('Van restored. Review a fresh recommendation before approval.')
    unavailable = state.festival_unavailable
    result = optimize(orders, quotes, unavailable, demo=True)
    state.festival_current_plan = result
    brief = assistant_brief(result, loaded=True, validated=True,
                            previewed=bool(state.get('festival_preview')),
                            approved=bool(state.get('festival_approved')),
                            prepared=bool(state.get('festival_prepared')),
                            last_change=state.get('festival_last_change'),
                            previous=state.get('festival_previous_plan'))
    st.info(f"{brief['stage']} · {brief['message']}\n\nNext action: {brief['next']}")
    st.write('Deterministic solver:', result['status'], '·', result['reason'])
    baseline = result['baseline_myr']
    left, right = st.columns(2)
    left.metric('All-parcel fictional baseline', f'RM {baseline:.2f}' if baseline is not None else 'NOT AVAILABLE')
    right.metric('Selected fictional plan', f"RM {result['total_myr']:.2f}" if result['total_myr'] is not None else 'NOT READY')
    if baseline is not None and result['total_myr'] is not None:
        st.caption(f"Fictional difference: RM {baseline - result['total_myr']:.2f}. This comparison uses the same eligible fictional quote set and deadlines.")
    if state.get('festival_last_change'):
        st.info(state.festival_last_change)
        previous = state.get('festival_previous_plan')
        if previous and previous.get('total_myr') is not None and result['total_myr'] is not None:
            old_ids = {item['quote_id'] for item in previous['selected']}
            new_ids = {item['quote_id'] for item in result['selected']}
            delta = result['total_myr'] - previous['total_myr']
            st.write(f"What changed: assumed plan RM {previous['total_myr']:.2f} → RM {result['total_myr']:.2f} "
                     f"({'+' if delta >= 0 else ''}{delta:.2f} MYR). "
                     f"Removed: {', '.join(sorted(old_ids - new_ids)) or 'none'}. "
                     f"Added: {', '.join(sorted(new_ids - old_ids)) or 'none'}.")
        elif previous and result['status'] == 'NOT READY':
            st.write('What changed: the previous fictional plan is no longer feasible; no replacement manifest is available.')
    st.write('Alternatives and constraints')
    st.dataframe(alternatives(orders, quotes, unavailable), hide_index=True)
    if result['status'] == 'NOT READY':
        uncovered = sorted(set(orders.order_id.astype(str)) - {
            oid for quote, checked in zip(quotes, result['reviewed']) if checked['status'] == 'ELIGIBLE'
            for oid in quote['shipment_ids']})
        st.warning('No complete eligible fictional plan. ' +
                   (f"No eligible quote covers {', '.join(uncovered)}. " if uncovered else '') +
                   'Adjust deadlines or restore provider availability; no manifest can be prepared.')
        with st.expander('Fictional decision history'):
            for event in state.festival_events:
                st.write(event)
        return
    st.write('Recommended shipment groups')
    st.dataframe(pd.DataFrame(result['decisions']), hide_index=True)
    st.caption('Costs, route stops, transit times and source references above are internal fictional assumptions.')
    if st.button('Preview five-order fictional plan'):
        state.festival_preview = preview(orders, quotes, unavailable, demo=True)
        state.festival_approved = None
        state.festival_prepared = False
        state.festival_events.append('FICTIONAL PLAN PROPOSED · no booking or payment')
        st.rerun()
    if state.get('festival_preview'):
        st.info('Reviewable proposal only. Current shipments are not approved or booked.')
        if st.button('Approve five-order fictional plan'):
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
    if state.get('festival_approved'):
        st.success('Fictional plan approved. No carrier has been contacted, booked, paid or dispatched.')
        table = manifest(orders, state.festival_approved)
        st.download_button('Download fictional preparation manifest — NOT A BOOKING',
                           table.to_csv(index=False), 'fictional_five_order_manifest.csv', 'text/csv')
        st.write('Next actions: verify real addresses and rates, pack and label the parcels, then request actual bookings outside this demonstration.')
        if not state.get('festival_prepared') and st.button('Mark fictional packages prepared'):
            state.festival_prepared = True
            state.festival_events.append('FICTIONAL PACKAGES MARKED PREPARED · no dispatch')
            st.rerun()
    with st.expander('Fictional decision history'):
        for event in state.festival_events:
            st.write(event)
