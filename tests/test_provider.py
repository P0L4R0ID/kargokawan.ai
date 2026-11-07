from unittest.mock import Mock, patch
from types import SimpleNamespace as NS
import pytest
from ai_provider import configuration, create_client, test_connection as check_connection
from agent import run_request, LogisticsAgent
from engine import sample_orders
from test_agent import mock_client
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize('provider,model,url', [('deepseek','deepseek-flash','https://api.deepseek.com'), ('openai','gpt-4o-mini','https://api.openai.com/v1')])
def test_provider_sdk_and_tool_protocol(monkeypatch,provider,model,url):
    monkeypatch.setenv('AI_PROVIDER',provider)
    monkeypatch.setenv(provider.upper()+'_API_KEY','test-placeholder')
    config = configuration()
    assert config['model']==model and config['ready']
    with patch('openai.OpenAI') as sdk:
        create_client(config)
        assert sdk.call_args.kwargs['base_url']==url
        assert sdk.call_args.kwargs['max_retries']==0
    client = mock_client()
    result = run_request('optimise',sample_orders(),client=client)
    assert result['provider']==provider and result['plan']
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs['model']==model
    assert not any(t['function'].get('strict') for t in kwargs['tools'])
    assert kwargs['timeout'] <= 12


def test_defaults_overrides_and_missing_keys(monkeypatch):
    assert configuration()['provider']=='deepseek'
    assert not check_connection()['ok']
    monkeypatch.setenv('DEEPSEEK_MODEL','custom-model')
    assert configuration()['model']=='custom-model'
    monkeypatch.setenv('OPENAI_API_KEY','test-placeholder')
    assert configuration()['provider']=='openai'
    monkeypatch.setenv('AI_PROVIDER','invalid')
    assert not configuration()['ready']
    assert run_request('optimise',sample_orders())['mode']=='Deterministic fallback'


def test_partial_failure_discards_proposal_and_keeps_budget():
    client = mock_client('simulate_disruption','{"provider":"Demo Consolidated Freight","available":false}')
    first = next(client.chat.completions.create.side_effect)
    client.chat.completions.create.side_effect = [first, TimeoutError('sensitive')]
    orders = sample_orders(); original = orders.copy()
    result = run_request('optimise',orders,client=client)
    assert result['proposal'] is None and orders.equals(original)
    assert result['trace'][0]['status']=='discarded'
    assert 'result' not in result['trace'][0]
    assert result['mode']=='Deterministic fallback' and result['plan']
    assert len(result['trace'])==3 and 'sensitive' not in str(result)


def test_invalid_change_clears_previous_proposal():
    agent = LogisticsAgent(sample_orders())
    agent.call('simulate_disruption',{'provider':'Demo Freight','available':False})
    assert agent.proposal
    agent.call('simulate_disruption',{'deadline_days':False})
    assert agent.proposal is None


def test_failure_at_limit_does_not_reset_budget():
    client = mock_client(repeats=True)
    first = next(client.chat.completions.create.side_effect)
    bad = mock_client('shell')
    rejected = next(bad.chat.completions.create.side_effect)
    client.chat.completions.create.side_effect = [first]*5+[rejected]
    result = run_request('optimise',sample_orders(),client=client)
    assert len(result['trace'])==6
    assert result['proposal'] is None and result['plan'] is None
    assert result['mode']=='Deterministic fallback'


def test_connection_single_actual_tool_and_redacted_failure():
    client = mock_client('inspect_orders')
    result = check_connection(client)
    assert result['ok'] and result['tool']=='inspect_orders' and result['sample_orders']==15
    assert client.chat.completions.create.call_count==1
    client = Mock(); client.chat.completions.create.side_effect=TimeoutError('private-value')
    result = check_connection(client)
    assert not result['ok'] and 'private-value' not in str(result)


def test_button_does_not_test_on_rerun():
    with patch('ai_provider.test_connection', return_value={'ok':True,'message':'SIMULATED test succeeded'}) as check:
        app = AppTest.from_file('../app.py',default_timeout=20).run()
        app.run()
        assert check.call_count==0
        next(b for b in app.button if b.label=='Test AI connection').click().run()
        assert check.call_count==1 and not app.exception
        app.run()
        assert check.call_count==1
