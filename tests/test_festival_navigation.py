"""Guided fictional stages remain grounded in the same solver and approval state."""
from decimal import Decimal
from streamlit.testing.v1 import AppTest


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception


def test_guided_journey_and_backward_navigation():
    app = AppTest.from_file('../app.py', default_timeout=30).run()
    assert len(app.session_state['festival_orders']) == 5
    assert app.session_state['festival_current_plan'] is None
    assert not any('Suggested total · assumed' == item.label for item in app.metric)
    assert not any(tab.label == 'Overview' for tab in app.tabs)
    assert app.session_state['festival_view'] == 'Orders'
    original_events = list(app.session_state['festival_events'])
    app.run()
    assert app.session_state['festival_events'] == original_events
    assert app.session_state['festival_current_plan'] is None
    click(app, 'Find the best delivery plan')
    assert app.session_state['festival_current_plan']['total_myr'] == Decimal('113.00')
    click(app, 'View orders')
    assert app.session_state['festival_view'] == 'Orders'
    click(app, 'Find the best delivery plan')
    click(app, 'Review this delivery plan')
    assert app.session_state['festival_view'] == 'Approve'
    assert not any('preparation manifest' in item.label for item in app.get('download_button'))
    click(app, 'Approve this plan')
    assert app.session_state['festival_view'] == 'Prepare'
    assert any('preparation manifest' in item.label for item in app.get('download_button'))
    click(app, 'View plan')
    assert app.session_state['festival_approved'] is not None
    click(app, 'Continue to preparation')
    click(app, 'Simulate van unavailable')
    assert app.session_state['festival_view'] == 'Plan'
    assert app.session_state['festival_approved'] is None
    assert app.session_state['festival_current_plan']['total_myr'] == Decimal('132.00')
    click(app, 'Reset demo to orders')
    assert app.session_state['festival_view'] == 'Orders'
    assert app.session_state['festival_current_plan'] is None
    assert app.session_state['festival_approved'] is None


def test_blocked_deadline_requires_correction():
    app = AppTest.from_file('../app.py', default_timeout=30).run()
    next(item for item in app.selectbox if item.label == 'Fictional order to adjust deadline').set_value('FEST004').run()
    next(item for item in app.number_input if item.label == 'Revised fictional deadline (days)').set_value(1).run()
    click(app, 'Apply fictional deadline change')
    assert app.session_state['festival_current_plan']['status'] == 'NOT READY'
    assert any('FEST004' in item.value for item in app.warning)
    assert not any(button.label == 'Approve this plan' for button in app.button)
    click(app, 'Review deliveries')
    assert app.session_state['festival_view'] == 'Orders'


def test_each_stage_has_its_own_information_hierarchy():
    app = AppTest.from_file('../app.py', default_timeout=30).run()
    assert app.session_state['festival_current_plan'] is None
    assert not any(item.label == 'Suggested total · assumed' for item in app.metric)
    click(app, 'Find the best delivery plan')
    assert any('<div class="kk-cost"' in item.value and 'RM 113.00' in item.value for item in app.markdown)
    choices = app.session_state['festival_current_plan']['decisions']
    assert sum(len(item['shipment_ids']) for item in choices) == 5
    assert choices and any(item['method'] == 'multi_stop_vehicle' for item in choices)
    click(app, 'Review this delivery plan')
    assert any('<div class="kk-decision"' in item.value and 'RM 113.00' in item.value for item in app.markdown)
    assert not any(item.label == 'Suggested total · assumed' for item in app.metric)
    assert not any('preparation manifest' in item.label for item in app.get('download_button'))
    click(app, 'Approve this plan')
    assert any('<div class="kk-approved"' in item.value for item in app.markdown)
    assert not any('<div class="kk-decision"' in item.value for item in app.markdown)
    assert any('preparation manifest' in item.label for item in app.get('download_button'))
    assert app.session_state['festival_prepared'] is False
    click(app, 'Mark fictional packages prepared')
    assert app.session_state['festival_prepared'] is True


def test_one_visible_demo_primary_action_per_stage():
    app = AppTest.from_file('../app.py', default_timeout=30).run()
    assert next(button for button in app.button if button.label == 'Find the best delivery plan').proto.type == 'primary'
    click(app, 'Find the best delivery plan')
    assert next(button for button in app.button if button.label == 'Review this delivery plan').proto.type == 'primary'
    click(app, 'Review this delivery plan')
    assert next(button for button in app.button if button.label == 'Approve this plan').proto.type == 'primary'
    assert next(button for button in app.button if button.label == 'Change plan').proto.type != 'primary'
    click(app, 'Approve this plan')
    assert next(button for button in app.get('download_button') if button.label.startswith('Download preparation manifest')).proto.type == 'primary'
    assert any(item.label == 'Preparation details' for item in app.expander)
    assert any(item.label == 'Activity history' for item in app.expander)
