"""OpenAI-compatible configuration. Never return credentials or raw API errors."""
import os


def configuration():
    explicit = os.getenv('AI_PROVIDER', '').strip().lower()
    # Preserve existing installations that only configure an OpenAI key.
    provider = explicit or ('openai' if os.getenv('OPENAI_API_KEY') and not os.getenv('DEEPSEEK_API_KEY') else 'deepseek')
    if provider not in ('deepseek', 'openai'):
        return {'provider':'unsupported', 'model':'', 'ready':False, 'key_name':'', 'error':'AI_PROVIDER must be deepseek or openai.'}
    deepseek = provider == 'deepseek'
    key_name = 'DEEPSEEK_API_KEY' if deepseek else 'OPENAI_API_KEY'
    return {'provider':provider, 'model':os.getenv('DEEPSEEK_MODEL' if deepseek else 'OPENAI_MODEL') or ('deepseek-flash' if deepseek else 'gpt-4o-mini'),
            'key_name':key_name, 'ready':bool(os.getenv(key_name)),
            'base_url':'https://api.deepseek.com' if deepseek else 'https://api.openai.com/v1', 'error':''}


def create_client(config):
    from openai import OpenAI
    return OpenAI(api_key=os.environ[config['key_name']], base_url=config['base_url'], timeout=12, max_retries=0)


def safe_error(exc):
    from openai import APITimeoutError, AuthenticationError, PermissionDeniedError, RateLimitError, APIConnectionError
    if isinstance(exc, (TimeoutError, APITimeoutError)): return 'AI request timed out.'
    if isinstance(exc, AuthenticationError): return 'AI authentication failed. Check the selected provider secret in environment settings.'
    if isinstance(exc, PermissionDeniedError): return 'AI access denied. Check provider permissions and the network allowlist.'
    if isinstance(exc, RateLimitError): return 'AI rate or account quota limit reached.'
    if isinstance(exc, APIConnectionError): return 'Cannot reach AI provider. Check network access.'
    return 'AI request failed or returned an invalid response. Check provider/model configuration.'


def test_connection(client=None):
    """Exactly one API request; only fictional samples; execute one real read-only tool."""
    from agent import LogisticsAgent, TOOLS
    from engine import sample_orders
    import json
    config = configuration()
    if client is None and not config['ready']:
        return {'ok':False, 'message':config['error'] or f"Missing {config['key_name']}; deterministic fallback is active."}
    try:
        client = client or create_client(config)
        response = client.chat.completions.create(model=config['model'], timeout=12, max_tokens=128,
            messages=[{'role':'user','content':'SIMULATED / FICTIONAL connection test. Call inspect_orders with empty arguments.'}],
            tools=[t for t in TOOLS if t['function']['name']=='inspect_orders'],
            tool_choice={'type':'function','function':{'name':'inspect_orders'}})
        calls = response.choices[0].message.tool_calls
        if not calls or len(calls)!=1 or calls[0].function.name!='inspect_orders':
            raise ValueError('Unexpected tool response')
        agent = LogisticsAgent(sample_orders())
        result = agent.call('inspect_orders', json.loads(calls[0].function.arguments))
        if 'error' in result: raise ValueError('Invalid arguments')
        return {'ok':True, 'message':f"{config['provider']} connection verified: actual KargoKawan inspect_orders tool executed on fictional samples.", 'tool':'inspect_orders', 'sample_orders':len(result['orders'])}
    except Exception as exc:
        return {'ok':False, 'message':safe_error(exc)}
