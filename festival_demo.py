"""Five-order fictional logistics walkthrough; session-only, never pilot evidence."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import streamlit as st

from hybrid_quotes import normalize
from mixed_method import optimize, preview, approve
from sample_intake import validate_complete
from festival_tasks import readiness, preparation_tasks, changed_orders
from focused_quotes import fingerprint

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
    state.festival_task_marks = {}
    state.festival_task_fingerprint = None
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


def recommendation_line(result, orders):
    """Summarise only the solver's selected, fully covered fictional route."""
    if result['status'] not in ('READY', 'SOLVER LIMITED'):
        return 'No complete delivery plan meets the current test constraints.'
    by_id = {str(row['order_id']): row for row in orders.to_dict('records')}
    parts = []
    parcels = []
    for choice in result['decisions']:
        ids = choice['shipment_ids']
        destinations = list(dict.fromkeys(by_id[oid]['destination'] for oid in ids))
        places = ', '.join(destinations)
        if choice['method'] == 'multi_stop_vehicle':
            parts.append(f"one vehicle for {len(ids)} delivery stops in {places}")
        else:
            parcels.append(places)
    if parcels:
        grouped = list(dict.fromkeys(parcels))
        descriptions = [f"{parcels.count(city)} {city} orders" if parcels.count(city) > 1 else city
                        for city in grouped]
        connector = ' plus ' if any(parcels.count(city) > 1 for city in grouped) else ' and '
        parts.append('separate parcels for ' + connector.join(descriptions) if len(parcels) > 1
                     else 'one parcel to ' + parcels[0])
    return 'Use ' + ' and '.join(parts) + '.'


def _view(state):
    """Navigation can inspect earlier steps, but never confer approval."""
    requested = state.get('festival_view', 'Orders')
    if state.get('festival_approved'):
        return requested if requested in ('Orders', 'Plan', 'Prepare') else 'Prepare'
    if state.get('festival_preview'):
        return requested if requested in ('Orders', 'Plan', 'Approve') else 'Approve'
    return requested if requested in ('Orders', 'Plan') else 'Plan'


def _go(state, stage):
    state.festival_view = stage
    st.rerun()


def _seed(state):
    state.festival_orders, state.festival_quotes = load_scenario()
    state.festival_unavailable = []
    state.festival_preview = None
    state.festival_approved = None
    state.festival_prepared = False
    state.festival_events = ['FICTIONAL INTAKE LOADED · no booking']
    state.festival_previous_plan = None
    state.festival_current_plan = None
    state.festival_last_change = None
    state.festival_view = 'Orders'
    state.festival_task_marks = {}
    state.festival_task_fingerprint = None


def _groups(result, orders):
    by_id = {str(row['order_id']): row for row in orders.to_dict('records')}
    for choice in sorted(result.get('decisions', []),
                         key=lambda item: (item['method'] != 'multi_stop_vehicle', item['shipment_ids'])):
        ids = choice['shipment_ids']
        cities = list(dict.fromkeys(by_id[oid]['destination'] for oid in ids))
        method = 'Van' if choice['method'] == 'multi_stop_vehicle' else 'Courier'
        with st.container(border=True):
            st.write(f"**{method} · {', '.join(cities)}**")
            st.write(f"RM {choice['total_myr']:.2f} assumed · {len(ids)} {'stops' if method == 'Van' else 'parcel'}")
            st.caption('Orders: ' + ', '.join(ids) + ' · ' + choice['service'])
            st.caption('Estimated delivery time after pickup: ' + str(next((q['transit_days'] for q in st.session_state.festival_quotes
                                                     if q['quote_id'] == choice['quote_id']), 'unknown')) +
                       ' day(s), based on fictional assumptions; not guaranteed.')


def _change_note(state, result):
    if not state.get('festival_last_change'):
        return
    previous = state.get('festival_previous_plan')
    if 'PROVIDER DISRUPTION' in state.festival_last_change:
        st.warning("The van is unavailable. I've updated your delivery plan. Please review it again.")
    elif 'PROVIDER RESTORED' in state.festival_last_change:
        st.warning('The van is available again. Please review the updated plan.')
    else:
        st.warning('Something changed. Please review the delivery plan again.')
    if previous and previous.get('total_myr') is not None and result['total_myr'] is not None:
        old_ids = {item['quote_id'] for item in previous['selected']}
        new_ids = {item['quote_id'] for item in result['selected']}
        delta = result['total_myr'] - previous['total_myr']
        st.write(f"Assumed cost: RM {previous['total_myr']:.2f} → RM {result['total_myr']:.2f} ({delta:+.2f} MYR).")
        changed = changed_orders(previous, result)
        if changed:
            names = {'multi_stop_vehicle': 'multi-stop van', 'parcel_courier': 'courier parcel'}
            st.caption('Changed deliveries: ' + '; '.join(f'{oid}: {names.get(old, old)} → {names.get(new, new)}'
                                                         for oid, old, new in changed) + '.')
        with st.expander('See changed option references'):
            st.write('Removed: ' + (', '.join(sorted(old_ids-new_ids)) or 'none'))
            st.write('Added: ' + (', '.join(sorted(new_ids-old_ids)) or 'none'))
    elif previous and result['status'] == 'NOT READY':
        st.write('The earlier plan no longer works. There is no replacement cost to compare.')


def render():
    state = st.session_state
    if state.get('festival_orders') is None:
        _seed(state)
    st.subheader('Your deliveries to arrange')
    st.caption('Demo uses fictional orders and prices. No real bookings.')
    orders, quotes = state.festival_orders, state.festival_quotes
    try:
        validate_orders(orders)
    except ValueError as exc:
        st.error('Please correct the delivery details before planning: ' + str(exc))
        return
    current_fingerprint = fingerprint(orders, quotes, []) + repr(sorted(state.festival_unavailable)) + repr(True)
    expected = state.get('festival_task_fingerprint') if state.get('festival_approved') else (
        state.festival_preview['fingerprint'] if state.get('festival_preview') else None)
    if expected and expected != current_fingerprint:
        _reset_plan(state, 'FICTIONAL INPUTS CHANGED · prior approval and tasks cleared')
        state.festival_view = 'Plan'
        st.rerun()
    stage = _view(state)
    state.festival_view = stage
    result = None
    if stage != 'Orders':
        result = optimize(orders, quotes, state.festival_unavailable, demo=True)
        state.festival_current_plan = result
    st.caption(readiness(orders, result or state.get('festival_current_plan'), previewed=bool(state.get('festival_preview')),
                         approved=bool(state.get('festival_approved')),
                         prepared=bool(state.get('festival_prepared'))))
    stages = ('Orders', 'Plan', 'Approve', 'Prepare')
    st.progress((stages.index(stage) + 1) * 25, text=f'Step {stages.index(stage)+1} of 4 · {stage}')
    with st.expander('Earlier steps', expanded=False):
        for back in stages[:stages.index(stage)]:
            if st.button('View ' + back.lower(), key='festival_back_'+back):
                _go(state, back)
    if stage == 'Orders':
        st.write(f"**You have {len(orders)} deliveries to arrange**")
        st.caption(f"Pickup: {orders.iloc[0]['origin']} {orders.iloc[0]['origin_postcode']} · "
                   f"{orders.destination.nunique()} destination cities. Delivery groups have not been chosen yet.")
        order_rows = orders.to_dict('records')
        for offset in range(0, len(order_rows), 2):
            for column, row in zip(st.columns(2), order_rows[offset:offset + 2]):
                with column.container(border=True):
                    st.write(f"**{row['destination']} · {row['destination_postcode']}**")
                    st.write(f"{row['order_id']} · Due in {row['deadline_days']} day(s)")
        with st.expander('Check complete order details and change a deadline'):
            st.dataframe(orders, hide_index=True)
            selected_id = st.selectbox('Fictional order to adjust deadline', orders.order_id.astype(str).tolist(),
                                       key='festival_deadline_order')
            current_days = int(orders.set_index('order_id').loc[selected_id, 'deadline_days'])
            new_days = st.number_input('Revised fictional deadline (days)', min_value=1, max_value=14,
                                       value=current_days, step=1, key='festival_deadline_value_' + selected_id)
            if st.button('Apply fictional deadline change'):
                changed = orders.copy()
                changed.loc[changed.order_id == selected_id, 'deadline_days'] = int(new_days)
                try:
                    state.festival_orders = validate_orders(changed)
                    _reset_plan(state, f'FICTIONAL DEADLINE CHANGED · {selected_id}: {current_days} → {int(new_days)} days')
                    state.festival_view = 'Plan'
                    st.rerun()
                except ValueError as exc:
                    st.error('Please correct this deadline: ' + str(exc))
        if st.button('Find the best delivery plan', type='primary'):
            _go(state, 'Plan')
    elif stage == 'Plan':
        st.write('**Delivery plan**')
        if result['status'] == 'NOT READY':
            uncovered = sorted(set(orders.order_id.astype(str)) - {
                oid for quote, checked in zip(quotes, result['reviewed']) if checked['status'] == 'ELIGIBLE'
                for oid in quote['shipment_ids']})
            reasons = list(dict.fromkeys(checked['reason'] for quote, checked in zip(quotes, result['reviewed'])
                                         if checked['status'] == 'EXCLUDED' and
                                         any(oid in quote['shipment_ids'] for oid in uncovered)))
            st.warning('No complete plan meets the current delivery needs. ' +
                       (f"No available option covers {', '.join(uncovered)}. " if uncovered else '') +
                       (f"Why: {reasons[0]} " if reasons else '') +
                       'Adjust the deadline or restore the van, then review again.')
            _change_note(state, result)
            if st.button('Review deliveries', type='primary'):
                _go(state, 'Orders')
        else:
            col1, col2, col3 = st.columns(3)
            col1.metric('Suggested total · assumed', f"RM {result['total_myr']:.2f}")
            col2.metric('All-courier comparison', f"RM {result['baseline_myr']:.2f}" if result['baseline_myr'] is not None else 'Not available')
            col3.metric('Deliveries covered', f"{len({oid for item in result['decisions'] for oid in item['shipment_ids']})} of {len(orders)}")
            if result['difference_myr'] is not None:
                st.caption(f"Assumed difference: RM {result['difference_myr']:.2f}, from the same eligible fictional options.")
            st.write(recommendation_line(result, orders))
            st.caption('Every order is covered once within its stated deadline. ' +
                     ('This is the lowest eligible assumed cost.' if result['status'] == 'READY' else
                      'This plan is feasible; lowest cost was not proven.'))
            _groups(result, orders)
            _change_note(state, result)
            if state.get('festival_preview'):
                if st.button('Continue to approval', type='primary'):
                    _go(state, 'Approve')
            elif state.get('festival_approved'):
                if st.button('Continue to preparation', type='primary'):
                    _go(state, 'Prepare')
            elif st.button('Review this delivery plan', type='primary'):
                state.festival_preview = preview(orders, quotes, state.festival_unavailable, demo=True)
                state.festival_events.append('FICTIONAL PLAN PROPOSED · no booking or payment')
                _go(state, 'Approve')
        with st.expander('How was this calculated?'):
            st.write('Solver:', result['status'], '·', result['reason'])
            st.dataframe(alternatives(orders, quotes, state.festival_unavailable), hide_index=True)
            if result.get('decisions'):
                st.dataframe(pd.DataFrame(result['decisions']), hide_index=True)
    elif stage == 'Approve':
        if not state.get('festival_preview') or result['status'] == 'NOT READY':
            _go(state, 'Plan')
        st.write('**Review and approve**')
        proposed = state.festival_preview['result']
        st.metric('Plan to approve · assumed', f"RM {proposed['total_myr']:.2f}")
        st.write(f"{len(orders)} orders · {len(proposed['decisions'])} delivery groups · " +
                 ', '.join('Van' if item['method'] == 'multi_stop_vehicle' else 'Courier'
                           for item in proposed['decisions']))
        st.caption('Approval lets KargoKawan prepare a shipment manifest. It does not book, pay for or dispatch deliveries.')
        with st.expander('View full plan details'):
            _groups(proposed, orders)
        if st.button('Approve this plan', type='primary'):
            try:
                state.festival_approved = approve_scenario(state.festival_preview, orders, quotes, state.festival_unavailable)
                state.festival_task_fingerprint = state.festival_preview['fingerprint']
                state.festival_task_marks = {}
                state.festival_preview = None
                state.festival_prepared = False
                state.festival_events.append('HUMAN APPROVED FICTIONAL PLAN · no booking or payment')
                _go(state, 'Prepare')
            except ValueError as exc:
                state.festival_preview = None
                state.festival_view = 'Plan'
                st.error('This plan changed. Review it again: ' + str(exc))
        if st.button('Change plan'):
            state.festival_preview = None
            state.festival_events.append('FICTIONAL PROPOSAL DISCARDED · no change to orders')
            _go(state, 'Plan')
    elif stage == 'Prepare':
        if not state.get('festival_approved'):
            _go(state, 'Plan')
        st.write('**Your plan is approved**')
        approved = state.festival_approved
        st.success(f"Plan approved for {len(orders)} fictional orders in {len(approved['decisions'])} groups. Nothing has been booked or dispatched.")
        st.metric('Approved assumed total', f"RM {approved['total_myr']:.2f}")
        table = manifest(orders, state.festival_approved)
        st.download_button('Download preparation manifest — NOT A BOOKING',
                           table.to_csv(index=False), 'fictional_five_order_manifest.csv', 'text/csv', type='primary')
        st.write('Next, use the manifest to prepare the parcels. Confirm real carrier prices and service before arranging any booking.')
        tasks = preparation_tasks(orders, approved)
        marks = state.setdefault('festival_task_marks', {})
        outstanding = [task for task in tasks if not marks.get(task['id'])]
        if outstanding:
            st.caption(f'{len(outstanding)} preparation prompts remain; carrier checks and bookings are outside this demo.')
        with st.expander('Preparation details'):
            for task in tasks:
                done = bool(marks.get(task['id']))
                st.write(f"{'Operator marked done' if done else task['priority']} · {task['title']}")
                st.caption(task['why'])
                if task['acknowledge'] and not done and st.button('Operator marked done: ' + task['title'], key='festival_task_'+task['id']):
                    marks[task['id']] = True
                    state.festival_events.append('FICTIONAL TASK OPERATOR MARKED DONE · ' + task['id'] + ' · no carrier confirmation')
                    st.rerun()
            if not state.get('festival_prepared') and st.button('Mark fictional packages prepared'):
                state.festival_prepared = True
                state.festival_events.append('FICTIONAL PACKAGES MARKED PREPARED · no dispatch')
                st.rerun()
        if state.get('festival_prepared'):
            st.info('Preparation marked in this session. No carrier has been contacted.')
    if stage != 'Orders':
        st.caption('Demo uses fictional orders and prices. No real bookings.')
    with st.expander('Something changed? · Demo controls and activity'):
        if st.button('Reset demo to orders'):
            _seed(state)
            st.rerun()
        if VAN not in state.festival_unavailable:
            if st.button('Simulate van unavailable'):
                state.festival_unavailable = [VAN]
                _reset_plan(state, 'FICTIONAL PROVIDER DISRUPTION · van unavailable; prior approval cleared')
                _go(state, 'Plan')
        elif st.button('Restore van'):
            state.festival_unavailable = []
            _reset_plan(state, 'FICTIONAL PROVIDER RESTORED · prior approval cleared')
            _go(state, 'Plan')
    with st.expander('Activity history'):
        _timeline(state.festival_events)
