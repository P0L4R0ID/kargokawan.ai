"""Guided fictional stages remain grounded in the same solver and approval state."""
from decimal import Decimal
from streamlit.testing.v1 import AppTest


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception


def test_guided_journey_and_backward_navigation():
    app = AppTest.from_file('../app.py', default_timeout=30).run()
    assert [tab.label for tab in app.tabs] == ['Five-order walkthrough', 'Private Pilot', 'Advanced & other demos']
    assert not any(tab.label == 'Overview' for tab in app.tabs)
    click(app, 'Try with 5 example deliveries')
    assert app.session_state['festival_view'] == 'Orders'
    click(app, 'Review delivery plan')
    assert app.session_state['festival_current_plan']['total_myr'] == Decimal('113.00')
    click(app, 'View orders')
    assert app.session_state['festival_view'] == 'Orders'
    click(app, 'Review delivery plan')
    click(app, 'Review this plan')
    assert app.session_state['festival_view'] == 'Approve'
    assert not any('fictional preparation manifest' in item.label for item in app.get('download_button'))
    click(app, 'Approve this plan')
    assert app.session_state['festival_view'] == 'Prepare'
    assert any('fictional preparation manifest' in item.label for item in app.get('download_button'))
    click(app, 'View plan')
    assert app.session_state['festival_approved'] is not None
    click(app, 'Continue to preparation')
    click(app, 'Simulate van unavailable')
    assert app.session_state['festival_view'] == 'Plan'
    assert app.session_state['festival_approved'] is None
    assert app.session_state['festival_current_plan']['total_myr'] == Decimal('132.00')


def test_blocked_deadline_requires_correction():
    app = AppTest.from_file('../app.py', default_timeout=30).run()
    click(app, 'Try with 5 example deliveries')
    next(item for item in app.selectbox if item.label == 'Fictional order to adjust deadline').set_value('FEST004').run()
    next(item for item in app.number_input if item.label == 'Revised fictional deadline (days)').set_value(1).run()
    click(app, 'Apply fictional deadline change')
    assert app.session_state['festival_current_plan']['status'] == 'NOT READY'
    assert any('FEST004' in item.value for item in app.warning)
    assert not any(button.label == 'Approve this plan' for button in app.button)
    click(app, 'Review deliveries')
    assert app.session_state['festival_view'] == 'Orders'
