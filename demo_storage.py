"""Session-scoped, disposable job path for the public demo UI only."""
import re
import secrets
from pathlib import Path


def demo_job_path(session_state, directory='.data'):
    nonce = session_state.get('demo_job_nonce')
    if not isinstance(nonce, str) or not re.fullmatch(r'[0-9a-f]{32}', nonce):
        nonce = secrets.token_hex(16)
        session_state['demo_job_nonce'] = nonce
    return Path(directory) / ('demo_jobs_' + nonce + '.sqlite')
