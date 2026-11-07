from types import SimpleNamespace as NS
from unittest.mock import Mock
import json
import pytest
from streamlit.testing.v1 import AppTest
from agent import LogisticsAgent, run_request, approve
from engine import sample_orders, solve, candidates


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)


def mock_client(name='optimise_shipments', arguments='{}', repeats=False):
    message = Mock()
    message.tool_calls = [NS(id='call1', function=NS(name=name, arguments=arguments))]
    message.model_dump.return_value = {'role':'assistant', 'tool_calls':[{'id':'call1','type':'function','function':{'name':name,'arguments':arguments}}]}
    client = Mock()
    first = NS(choices=[NS(message=message)])
    last = NS(choices=[NS(message=NS(tool_calls=[], content='Invented price RM 1 and ETA 0'))])
    client.chat.completions.create.side_effect = [first]*7 if repeats else [first,last]
    return client


@pytest.mark.parametrize('name,args', [('exec',{}), ('optimise_shipments',{'cost':1}), ('simulate_disruption',{'provider':'Real Carrier','available':False}), ('simulate_disruption',{'order_id':'KK001','deadline_days':0}), ('simulate_disruption',{'order_id':'KK001','deadline_days':True}), ('inspect_orders',None)])
def test_schema_validation(name,args):
    agent = LogisticsAgent(sample_orders())
    assert 'error' in agent.call(name,args)
    assert agent.proposal is None


def test_fallback_optimisation_and_grounding():
    df = sample_orders()
    answer = run_request('Optimise these orders and explain why this plan is cheaper.', df)
    assert answer['mode'] == 'Deterministic fallback'
    assert answer['plan']['cost_rm'] == solve(df)['total']
    options = candidates(df)
    for p in answer['plan']['groups']:
        assert any(p['provider']==o.provider and p['cost']==o.cost and p['eta_days']==o.eta_days and p['ids']==o.ids for o in options)


def test_read_only_tightest_deadlines():
    answer = run_request('Which shipments have the tightest deadlines?', sample_orders())
    rows = answer['trace'][0]['result']['orders']
    assert rows[0]['deadline_days'] == 2
    assert answer['proposal'] is None and answer['plan'] is None


def test_preview_approval_rejection_and_stale_state():
    df = sample_orders(); original = df.copy(deep=True)
    answer = run_request('What if Demo Consolidated Freight is unavailable?', df)
    proposal = answer['proposal']
    assert df.equals(original)
    assert proposal['disabled'] == ['Demo Consolidated Freight']
    assert all(p['provider'] != 'Demo Consolidated Freight' for p in proposal['after']['groups'])
    with pytest.raises(ValueError, match='approval'): approve(proposal,df,[])
    updated, disabled = approve(proposal,df,[],True)
    assert updated.equals(df) and disabled == proposal['disabled']
    df.loc[0,'deadline_days'] = 3
    with pytest.raises(ValueError, match='fresh preview'): approve(proposal,df,[],True)


def test_deadline_preview_and_infeasibility():
    agent = LogisticsAgent(sample_orders())
    result = agent.call('simulate_disruption',{'order_id':'KK001','deadline_days':3})
    assert result['after']['deadlines'][0:]
    assert agent.orders.loc[0,'deadline_days'] == 10
    assert 'error' in agent.call('simulate_disruption',{'order_id':'KK001','deadline_days':1})
    assert agent.proposal is None


def test_mock_llm_and_no_invented_prose():
    answer = run_request('optimise',sample_orders(),client=mock_client())
    assert answer['mode'] == 'LLM tool orchestration'
    assert answer['plan']['cost_rm'] == solve(sample_orders())['total']
    assert 'Invented price' not in str(answer)


@pytest.mark.parametrize('name,args', [('shell','{}'), ('optimise_shipments','bad json'), ('simulate_disruption','{"provider":"Fake","available":false}')])
def test_invalid_model_calls(name,args):
    answer = run_request('optimise',sample_orders(),client=mock_client(name,args))
    assert answer['trace'][0]['status'] == 'rejected'
    assert answer['proposal'] is None


def test_tool_limit():
    client = mock_client(repeats=True)
    answer = run_request('optimise',sample_orders(),client=client)
    assert len(answer['trace']) == 6
    assert client.chat.completions.create.call_count == 6


def test_api_error_falls_back():
    client = Mock(); client.chat.completions.create.side_effect = TimeoutError('secret error')
    answer = run_request('optimise', sample_orders(), client=client)
    assert answer['mode'] == 'Deterministic fallback' and answer['plan']
    assert 'secret error' not in str(answer)


def test_invalid_city():
    df = sample_orders(); df.loc[0,'origin'] = 'Atlantis'
    with pytest.raises(ValueError): run_request('optimise',df)


def test_ui_preview_discard_and_apply():
    app = AppTest.from_file('../app.py', default_timeout=20).run()
    app.text_input[0].set_value('What if Demo Consolidated Freight is unavailable?')
    next(b for b in app.button if b.label == 'Ask assistant').click().run()
    assert not app.exception and app.multiselect[0].value == []
    next(b for b in app.button if b.label == 'Discard').click().run()
    assert not app.exception and app.multiselect[0].value == []
    next(b for b in app.button if b.label == 'Ask assistant').click().run()
    next(b for b in app.button if b.label == 'Apply proposed change').click().run()
    assert not app.exception
    assert app.multiselect[0].value == ['Demo Consolidated Freight']
    assert len(app.metric) == 4
