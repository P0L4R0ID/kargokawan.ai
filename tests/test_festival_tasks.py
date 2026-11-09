"""Fictional coordination remains tied to approved solver output."""
from decimal import Decimal
from streamlit.testing.v1 import AppTest

from festival_demo import VAN, load_scenario
from festival_tasks import changed_orders, preparation_tasks, readiness
from mixed_method import optimize


def _click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception


def test_tasks_come_from_selected_groups_and_deadlines():
    orders, quotes = load_scenario()
    plan = optimize(orders, quotes, demo=True)
    tasks = preparation_tasks(orders, plan)
    selected = {choice['quote_id'] for choice in plan['decisions']}
    assert {task['id'].split(':')[0] for task in tasks if ':' in task['id']} == selected
    assert len(tasks) == 4 * len(selected) + 2
    assert tasks[0]['priority'] == 'External check'
    assert all('day(s)' in task['why'] for task in tasks if task['id'].endswith(':deadline'))
    assert all(not task['acknowledge'] for task in tasks if task['id'].endswith(':carrier'))
    assert not next(task for task in tasks if task['id'] == 'bookings')['acknowledge']
    assert not next(task for task in tasks if task['id'] == 'manifest')['acknowledge']
    assert preparation_tasks(orders, None) == []
    assert 'approval pending' in readiness(orders, plan, previewed=True)
    assert 'External bookings not performed' in readiness(orders, plan, approved=True)


def test_disruption_replaces_group_tasks_and_methods():
    orders, quotes = load_scenario()
    original = optimize(orders, quotes, demo=True)
    changed = optimize(orders, quotes, [VAN], demo=True)
    assert original['total_myr'] == Decimal('113.00')
    assert changed['total_myr'] == Decimal('132.00')
    assert {oid for oid, _, _ in changed_orders(original, changed)} == {'FEST001', 'FEST002', 'FEST003'}
    old_ids = {task['id'] for task in preparation_tasks(orders, original)}
    new_ids = {task['id'] for task in preparation_tasks(orders, changed)}
    assert 'FICTIONAL-VAN-KV-3:carrier' in old_ids - new_ids
    assert 'FICTIONAL-PARCEL-FEST001:carrier' in new_ids - old_ids


def test_task_marks_are_session_only_and_do_not_claim_carrier_completion():
    app = AppTest.from_file('../app.py', default_timeout=30).run()
    _click(app, 'Find the best delivery plan')
    _click(app, 'Review this delivery plan')
    _click(app, 'Approve this plan')
    assert app.session_state['festival_task_marks'] == {}
    task = next(button for button in app.button if button.label.startswith('Operator marked done: '))
    task_id = next(item['id'] for item in preparation_tasks(app.session_state['festival_orders'],
                    app.session_state['festival_approved']) if item['title'] in task.label)
    task.click().run()
    assert app.session_state['festival_task_marks'][task_id] is True
    events = list(app.session_state['festival_events'])
    assert events[-1].startswith('FICTIONAL TASK OPERATOR MARKED DONE')
    app.run()
    assert app.session_state['festival_events'] == events
    assert app.session_state['festival_task_marks'][task_id] is True
    assert not any('bookings' in button.label.lower() or 'payable cost' in button.label.lower()
                   for button in app.button if button.label.startswith('Operator marked done: '))
    _click(app, 'Simulate van unavailable')
    assert app.session_state['festival_task_marks'] == {}
    assert app.session_state['festival_approved'] is None
    assert not any('preparation manifest' in item.label for item in app.get('download_button'))
    _click(app, 'Review this delivery plan')
    _click(app, 'Approve this plan')
    assert any(task['id'].startswith('FICTIONAL-PARCEL-FEST001') for task in preparation_tasks(
        app.session_state['festival_orders'], app.session_state['festival_approved']))
