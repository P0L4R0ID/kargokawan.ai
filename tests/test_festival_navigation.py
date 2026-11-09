"""The public walkthrough stays usable across Streamlit reruns and tabs."""
from decimal import Decimal

from streamlit.testing.v1 import AppTest


def _button(app, label):
    return next(button for button in app.button if button.label == label)


def test_default_workspace_and_navigation_preserve_primary_flow():
    app = AppTest.from_file('../app.py', default_timeout=30).run()
    assert [tab.label for tab in app.tabs] == [
        'Five-order walkthrough', 'Private Pilot', 'Advanced & other demos']
    assert not app.exception
    _button(app, 'Load five-order fictional scenario').click().run()
    assert [tab.label for tab in app.tabs if tab.label in (
        'Overview', 'Delivery orders', 'Plan & compare', 'Review & approve', 'Activity')] == [
        'Overview', 'Delivery orders', 'Plan & compare', 'Review & approve', 'Activity']
    assert app.session_state['festival_approved'] is None
    assert app.session_state['festival_current_plan']['total_myr'] == Decimal('113.00')
    metrics = {item.label: item.value for item in app.metric}
    plan = app.session_state['festival_current_plan']
    assert metrics['Recommended assumed cost'] == f"RM {plan['total_myr']:.2f}"
    assert metrics['Eligible parcel baseline'] == f"RM {plan['baseline_myr']:.2f}"
    assert metrics['Assumed difference'] == f"RM {plan['difference_myr']:.2f}"
    assert metrics['Deliveries covered'] == '5 of 5'
    _button(app, 'Preview five-order fictional plan').click().run()
    assert app.session_state['festival_preview'] is not None
    assert not any(item.label.startswith('Download fictional preparation manifest')
                   for item in app.get('download_button'))
    _button(app, 'Approve five-order fictional plan').click().run()
    assert app.session_state['festival_approved']['total_myr'] == Decimal('113.00')
    assert any(item.label.startswith('Download fictional preparation manifest')
               for item in app.get('download_button'))
    _button(app, 'Simulate fictional van disruption').click().run()
    assert app.session_state['festival_approved'] is None
    assert app.session_state['festival_preview'] is None
    assert any('What changed: assumed plan RM 113.00 → RM 132.00' in item.value for item in app.markdown)
    assert not any(item.label.startswith('Download fictional preparation manifest')
                   for item in app.get('download_button'))


def test_blocked_deadline_is_readable_in_redesigned_workspace():
    app = AppTest.from_file('../app.py', default_timeout=30).run()
    _button(app, 'Load five-order fictional scenario').click().run()
    next(item for item in app.selectbox if item.label == 'Fictional order to adjust deadline').set_value('FEST004').run()
    next(item for item in app.number_input if item.label == 'Revised fictional deadline (days)').set_value(1).run()
    _button(app, 'Apply fictional deadline change').click().run()
    assert app.session_state['festival_approved'] is None
    metrics = {item.label: item.value for item in app.metric}
    assert metrics['Recommended assumed cost'] == 'NOT READY'
    assert metrics['Eligible parcel baseline'] == 'Not available'
    assert metrics['Assumed difference'] == 'Not available'
    assert any('No eligible quote covers FEST004' in item.value for item in app.warning)
    assert not any(button.label == 'Preview five-order fictional plan' for button in app.button)
