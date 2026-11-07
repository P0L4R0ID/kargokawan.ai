"""Dashboard orchestration; all provider, cost and ETA data is fictional."""
import hashlib
import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from engine import agent_run, sample_orders, validate, to_table

PROVIDERS = ['Demo Economy Courier', 'Demo Express Courier', 'Demo Freight',
             'Demo Consolidated Freight', 'Demo Multi-stop Van']
COLUMNS = list(sample_orders().columns)


def normalize(df):
    if any(c not in df for c in COLUMNS):
        raise ValueError('Required CSV columns: ' + ', '.join(COLUMNS))
    df = df[COLUMNS].copy()
    for c in COLUMNS[:3]:
        if df[c].isna().any() or df[c].astype(str).str.strip().eq('').any():
            raise ValueError(f'{c} cannot be blank.')
        df[c] = df[c].astype(str).str.strip()
    for c in COLUMNS[3:]:
        df[c] = pd.to_numeric(df[c], errors='coerce')
        if not np.isfinite(df[c]).all():
            raise ValueError(f'{c} must contain finite numbers.')
    return validate(df)


def fingerprint(df, disabled):
    return hashlib.sha256((df.to_csv(index=False) + json.dumps(sorted(disabled))).encode()).hexdigest()


def replan(state, df, disabled, force=False):
    signature = fingerprint(df, disabled)
    if not force and signature == state.get('signature'):
        return False
    previous = state.get('result')
    prior_orders = state.get('input_csv')
    prior_disabled = state.get('disabled', [])
    triggers = []
    if prior_orders != df.to_csv(index=False):
        triggers.append('Shipment orders / delivery deadlines changed' if prior_orders else 'Initial planning')
    if sorted(disabled) != prior_disabled:
        triggers.append('Fictional carrier availability changed')
    event = {'time': datetime.now(timezone.utc).isoformat(), 'trigger': '; '.join(triggers) or 'Manual planning',
             'input_csv': df.to_csv(index=False), 'disabled': sorted(disabled)}
    state.update(signature=signature, input_csv=event['input_csv'], disabled=sorted(disabled), result=None, error=None)
    try:
        result, steps = agent_run(normalize(df), disabled)
        event.update(status='Planned', cost=result['total'], steps=steps,
                     delta=round(result['total']-previous['total'], 2) if previous else None)
        state['result'] = result
    except ValueError as exc:
        state['error'] = str(exc)
        event.update(status='Blocked', cost=None, steps=[str(exc)], delta=None)
    state.setdefault('history', []).append(event)
    return True


def manifest(result):
    table = to_table(result['selected']).rename(columns={'Provider':'Fictional provider', 'Cost (RM)':'Simulated cost (RM)', 'ETA (days)':'Simulated ETA (days)'})
    table.insert(0, 'Data status', 'SIMULATED / FICTIONAL — NOT A BOOKING')
    return table
