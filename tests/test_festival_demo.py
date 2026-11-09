"""Five-order fictional operations walkthrough; no carrier or pilot writes."""
from decimal import Decimal
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from festival_demo import (LABEL, VAN, approve_scenario, alternatives, assistant_brief, recommendation_line,
                           load_scenario, manifest, validate_orders)
from hybrid_quotes import review
from mixed_method import optimize, preview
from pilot_api import _quote as pilot_quote_validator


def test_five_order_intake_quote_coverage_and_optimised_decision():
    orders, quotes = load_scenario()
    assert len(orders) == 5 and orders.order_id.is_unique
    assert validate_orders(orders).equals(orders)
    assert set(orders.destination_postcode) == {'50100', '50450', '51000', '10000', '80000'}
    assert all(quote['source_class'] == 'SYNTHETIC' and LABEL in quote['source_reference'] for quote in quotes)
    van = next(quote for quote in quotes if quote['provider'] == VAN)
    assert van['shipment_ids'] == ('FEST001', 'FEST002', 'FEST003')
    assert [stop['sequence'] for stop in van['dropoff_locations']] == [1, 2, 3]
    assert [stop['postcode'] for stop in van['dropoff_locations']] == ['50100', '50450', '51000']
    assert review(van, orders.to_dict('records'))['status'] == 'ELIGIBLE'
    result = optimize(orders, quotes, demo=True)
    assert result['status'] == 'READY'
    assert result['baseline_myr'] == Decimal('132.00')
    assert result['total_myr'] == Decimal('113.00')
    assert {item['quote_id'] for item in result['selected']} == {
        'FICTIONAL-VAN-KV-3', 'FICTIONAL-PARCEL-FEST004', 'FICTIONAL-PARCEL-FEST005'}
    assert sorted(oid for item in result['selected'] for oid in item['shipment_ids']) == sorted(orders.order_id)
    assert alternatives(orders, quotes).Review.value_counts().to_dict() == {'ELIGIBLE': 6, 'EXCLUDED': 2}
    assert optimize(orders, quotes)['status'] == 'NOT READY'
    with pytest.raises(ValueError):
        pilot_quote_validator({'source_class': 'SYNTHETIC', 'provider': VAN,
                               'service': 'Fictional', 'source_reference': LABEL})


def test_explicit_approval_manifest_and_disruption_replanning():
    orders, quotes = load_scenario()
    proposal = preview(orders, quotes, demo=True)
    with pytest.raises(ValueError, match='Approve'):
        manifest(orders, None)
    approved = approve_scenario(proposal, orders, quotes)
    table = manifest(orders, approved)
    assert len(table) == 5 and table['Order ID'].is_unique
    assert table['Status'].str.contains('FICTIONAL.*NOT A BOOKING').all()
    assert not any('TRACKING' in str(value).upper() for value in table.columns)
    assert 'FICTIONAL RECIPIENT' in table['Fictional recipient'][0]
    disrupted = optimize(orders, quotes, [VAN], demo=True)
    assert disrupted['status'] == 'READY' and disrupted['total_myr'] == Decimal('132.00')
    assert all(item['method'] == 'parcel_courier' for item in disrupted['decisions'])
    with pytest.raises(ValueError, match='fresh'):
        approve_scenario(proposal, orders, quotes, [VAN])
    replacement = approve_scenario(preview(orders, quotes, [VAN], demo=True), orders, quotes, [VAN])
    assert len(manifest(orders, replacement)) == 5


def test_deadline_change_and_missing_quote_are_honest_not_ready():
    orders, quotes = load_scenario()
    changed = orders.copy()
    changed.loc[changed.order_id == 'FEST004', 'deadline_days'] = 1
    changed = validate_orders(changed)
    result = optimize(changed, quotes, demo=True)
    assert result['status'] == 'NOT READY' and result['baseline_myr'] is None
    assert result['total_myr'] is None
    assert optimize(orders, [q for q in quotes if 'FEST005' not in q['shipment_ids']], demo=True)['status'] == 'NOT READY'
    with pytest.raises(ValueError, match='fresh'):
        approve_scenario(preview(orders, quotes, demo=True), changed, quotes)
    bad = orders.copy()
    bad.loc[0, 'origin_postcode'] = '5000'
    with pytest.raises(ValueError, match='postcode'):
        validate_orders(bad)
    bad = orders.copy()
    bad.loc[0, 'weight_kg'] = -1
    with pytest.raises(ValueError):
        validate_orders(bad)


def test_festival_ui_complete_flow_and_session_isolation():
    with patch('pilot_client.call_pilot', side_effect=AssertionError('private pilot API must not be called')):
        app = AppTest.from_file('../app.py', default_timeout=30).run()
        assert not app.exception
        next(b for b in app.button if b.label == 'Load five-order fictional scenario').click().run()
        assert not app.exception and len(app.session_state['festival_orders']) == 5
        assert app.session_state['festival_approved'] is None
        assert not any(b.label == 'Download fictional preparation manifest — NOT A BOOKING' for b in app.get('download_button'))
        next(b for b in app.button if b.label == 'Preview five-order fictional plan').click().run()
        assert app.session_state['festival_preview'] is not None
        assert app.session_state['festival_approved'] is None
        next(b for b in app.button if b.label == 'Approve five-order fictional plan').click().run()
        assert app.session_state['festival_approved']['total_myr'] == Decimal('113.00')
        assert any(b.label == 'Download fictional preparation manifest — NOT A BOOKING' for b in app.get('download_button'))
        next(b for b in app.button if b.label == 'Mark fictional packages prepared').click().run()
        assert app.session_state['festival_prepared'] is True
        next(b for b in app.button if b.label == 'Simulate fictional van disruption').click().run()
        assert app.session_state['festival_approved'] is None
        assert app.session_state['festival_prepared'] is False
        assert app.session_state['festival_unavailable'] == [VAN]
        assert any('What changed: assumed plan RM 113.00 → RM 132.00' in item.value for item in app.markdown)
        next(b for b in app.button if b.label == 'Preview five-order fictional plan').click().run()
        next(b for b in app.button if b.label == 'Approve five-order fictional plan').click().run()
        assert app.session_state['festival_approved']['total_myr'] == Decimal('132.00')


def test_festival_ui_impossible_deadline_blocks_approval():
    app = AppTest.from_file('../app.py', default_timeout=30).run()
    next(b for b in app.button if b.label == 'Load five-order fictional scenario').click().run()
    next(box for box in app.selectbox if box.label == 'Fictional order to adjust deadline').set_value('FEST004').run()
    next(item for item in app.number_input if item.label == 'Revised fictional deadline (days)').set_value(1).run()
    next(b for b in app.button if b.label == 'Apply fictional deadline change').click().run()
    assert not app.exception
    assert app.session_state['festival_approved'] is None
    assert not any(b.label == 'Preview five-order fictional plan' for b in app.button)
    assert any('No complete eligible fictional plan' in w.value for w in app.warning)


def test_assistant_uses_solver_decisions_and_actual_comparison():
    orders, quotes = load_scenario()
    result = optimize(orders, quotes, demo=True)
    brief = assistant_brief(result, loaded=True, validated=True)
    assert brief['stage'] == 'Plan ready'
    for decision in result['decisions']:
        assert decision['service'] in brief['message']
        assert ', '.join(decision['shipment_ids']) in brief['message']
        assert f"RM {decision['total_myr']:.2f}" in brief['message']
    assert f"RM {result['baseline_myr']:.2f}" in brief['message']
    assert f"RM {result['difference_myr']:.2f}" in brief['message']
    assert 'guaranteed' not in brief['message'].lower()
    assert 'booked' not in brief['message'].lower()
    assert 'paid' not in brief['message'].lower()


def test_assistant_transitions_and_disruption_reset():
    orders, quotes = load_scenario()
    result = optimize(orders, quotes, demo=True)
    assert assistant_brief()['stage'] == 'Start'
    assert assistant_brief(loaded=True)['stage'] == 'Blocked'
    assert assistant_brief(None, loaded=True, validated=True)['stage'] == 'Orders checked'
    assert assistant_brief(result, loaded=True, validated=True, previewed=True)['stage'] == 'Awaiting approval'
    assert assistant_brief(result, loaded=True, validated=True, approved=True)['stage'] == 'Approved'
    assert assistant_brief(result, loaded=True, validated=True, approved=True, prepared=True)['stage'] == 'Preparation started'
    changed = optimize(orders, quotes, [VAN], demo=True)
    brief = assistant_brief(changed, loaded=True, validated=True, last_change='Van unavailable', previous=result)
    assert brief['stage'] == 'Replan required'
    assert f"{changed['total_myr'] - result['total_myr']:+.2f} MYR" in brief['message']
    assert 'earlier approval was cleared' in brief['message']
    assert 'approve' in brief['next'].lower() or 'approval' in brief['next'].lower()


def test_assistant_blocked_and_missing_baseline_make_no_savings_claim():
    orders, quotes = load_scenario()
    changed = orders.copy()
    changed.loc[changed.order_id == 'FEST004', 'deadline_days'] = 1
    result = optimize(changed, quotes, demo=True)
    brief = assistant_brief(result, loaded=True, validated=True)
    assert brief['stage'] == 'Blocked'
    assert 'RM ' not in brief['message']
    van_only = [q for q in quotes if q['transport_method'] == 'multi_stop_vehicle']
    incomplete = optimize(orders, van_only, demo=True)
    assert assistant_brief(incomplete, loaded=True, validated=True)['stage'] == 'Blocked'
    limited = dict(optimize(orders, quotes, demo=True), status='SOLVER LIMITED')
    assert 'did not prove' in assistant_brief(limited, loaded=True, validated=True)['message']


def test_assistant_ui_history_tracks_only_actual_actions():
    app = AppTest.from_file('../app.py', default_timeout=30).run()
    next(b for b in app.button if b.label == 'Load five-order fictional scenario').click().run()
    assert app.session_state['festival_events'] == ['FICTIONAL INTAKE LOADED · no booking']
    assert any('Next action:' in item.value for item in app.markdown)

    next(b for b in app.button if b.label == 'Preview five-order fictional plan').click().run()
    assert app.session_state['festival_events'][-1].startswith('FICTIONAL PLAN PROPOSED')
    next(b for b in app.button if b.label == 'Discard five-order fictional proposal').click().run()
    assert app.session_state['festival_approved'] is None
    assert app.session_state['festival_events'][-1].startswith('FICTIONAL PROPOSAL DISCARDED')
    next(b for b in app.button if b.label == 'Preview five-order fictional plan').click().run()
    next(b for b in app.button if b.label == 'Approve five-order fictional plan').click().run()
    assert app.session_state['festival_events'][-1].startswith('HUMAN APPROVED')
    assert any(b.label == 'Download fictional preparation manifest — NOT A BOOKING' for b in app.get('download_button'))
    next(b for b in app.button if b.label == 'Simulate fictional van disruption').click().run()
    assert app.session_state['festival_events'][-1].startswith('FICTIONAL PROVIDER DISRUPTION')
    assert app.session_state['festival_approved'] is None
    assert not any(b.label == 'Download fictional preparation manifest — NOT A BOOKING' for b in app.get('download_button'))


def test_recommendation_copy_comes_from_selected_orders_and_methods():
    orders, quotes = load_scenario()
    plan = optimize(orders, quotes, demo=True)
    line = recommendation_line(plan, orders)
    assert '3 delivery stops in Kuala Lumpur' in line
    assert 'George Town and Johor Bahru' in line
    disrupted = optimize(orders, quotes, [VAN], demo=True)
    assert 'vehicle' not in recommendation_line(disrupted, orders)
    assert 'George Town' in recommendation_line(disrupted, orders)
    changed = orders.copy()
    changed.loc[changed.order_id == 'FEST004', 'deadline_days'] = 1
    blocked = optimize(changed, quotes, demo=True)
    assert 'No complete delivery plan' in recommendation_line(blocked, changed)
