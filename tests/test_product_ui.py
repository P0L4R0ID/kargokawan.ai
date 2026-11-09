"""Presentation stays grounded in solver results and escapes order text."""
from unittest.mock import patch

from festival_demo import load_scenario
from mixed_method import optimize
from product_ui import cost_panel, order_card, route_card


def test_cost_panel_uses_actual_plan_and_omits_missing_baseline():
    orders, quotes = load_scenario()
    plan = optimize(orders, quotes, demo=True)
    with patch('product_ui.st.markdown') as render:
        cost_panel(plan['total_myr'], plan['baseline_myr'], plan['difference_myr'], len(orders))
    html = render.call_args.args[0]
    assert f"RM {plan['total_myr']:.2f}" in html
    assert f"RM {plan['baseline_myr']:.2f}" in html
    assert f"RM {plan['difference_myr']:.2f}" in html
    with patch('product_ui.st.markdown') as render:
        cost_panel(plan['total_myr'], None, None, len(orders))
    html = render.call_args.args[0]
    assert 'comparison unavailable' in html
    assert 'RM None' not in html


def test_cards_escape_untrusted_order_and_destination_text():
    orders, quotes = load_scenario()
    malicious = orders.copy()
    malicious.loc[0, 'destination'] = '<script>alert(1)</script>'
    with patch('product_ui.st.markdown') as render:
        order_card(malicious.iloc[0].to_dict())
    assert '<script>' not in render.call_args.args[0]
    assert '&lt;script&gt;' in render.call_args.args[0]
    plan = optimize(orders, quotes, demo=True)
    choice = plan['decisions'][0]
    quote = next(q for q in quotes if q['quote_id'] == choice['quote_id'])
    with patch('product_ui.st.markdown') as render:
        route_card(choice, malicious, quote)
    assert '<script>' not in render.call_args.args[0]
