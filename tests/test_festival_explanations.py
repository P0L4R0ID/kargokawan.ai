"""Recommendation reasons never invent prices, speed objectives or guarantees."""
from decimal import Decimal

from streamlit.testing.v1 import AppTest

from festival_demo import VAN, load_scenario
from festival_explanations import plan_reasons
from mixed_method import optimize


def test_standard_plan_reasons_match_selected_costs_and_deadlines():
    orders, quotes = load_scenario()
    result = optimize(orders, quotes, demo=True)
    reasons = plan_reasons(orders, quotes, result)
    assert len(reasons) == 4
    assert 'cost, not delivery speed' in reasons[0]
    assert 'covered within its deadline' in reasons[0]
    assert f"RM {result['total_myr']:.2f}" in reasons[1]
    assert f"RM {result['baseline_myr']:.2f}" in reasons[1]
    assert f"RM {result['difference_myr']:.2f}" in reasons[1]
    van = next(item for item in result['decisions'] if item['method'] == 'multi_stop_vehicle')
    assert f"groups {len(van['shipment_ids'])} orders" in reasons[2]
    assert 'zero day of buffer' in reasons[3]
    assert 'FEST001' in reasons[3]
    assert 'not guaranteed' in reasons[3]
    assert not any('fastest' in reason.lower() or 'guaranteed savings' in reason.lower() for reason in reasons)


def test_disruption_reasons_use_all_courier_replacement():
    orders, quotes = load_scenario()
    result = optimize(orders, quotes, [VAN], demo=True)
    reasons = plan_reasons(orders, quotes, result)
    assert result['total_myr'] == result['baseline_myr'] == Decimal('132.00')
    assert 'No multi-stop vehicle is selected' in reasons[2]
    assert 'FEST001' in reasons[3] and 'FEST002' in reasons[3] and 'FEST003' in reasons[3]


def test_missing_baseline_solver_limit_and_blocked_result_are_honest():
    orders, quotes = load_scenario()
    result = optimize(orders, quotes, demo=True)
    without_baseline = dict(result, baseline_myr=None, difference_myr=None)
    reasons = plan_reasons(orders, quotes, without_baseline)
    assert 'No valid all-parcel comparison' in reasons[1]
    assert 'RM 132' not in ' '.join(reasons)
    limited = dict(result, status='SOLVER LIMITED')
    assert 'did not prove' in plan_reasons(orders, quotes, limited)[0]
    changed = orders.copy()
    changed.loc[changed.order_id == 'FEST004', 'deadline_days'] = 1
    blocked = optimize(changed, quotes, demo=True)
    assert blocked['status'] == 'NOT READY'
    assert plan_reasons(changed, quotes, blocked) == []


def test_plan_screen_shows_native_reason_list_only_for_ready_plan():
    app = AppTest.from_file('../app.py', default_timeout=30).run()
    next(button for button in app.button if button.label == 'Find the best delivery plan').click().run()
    assert not app.exception
    assert any('Why KargoKawan recommends this plan' in item.value for item in app.markdown)
    assert any('cost, not delivery speed' in item.value for item in app.markdown)
    assert not any('Why KargoKawan recommends this plan' in item.value for item in app.warning)
