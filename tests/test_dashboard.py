import io
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from dashboard import normalize, replan, manifest, PROVIDERS
from engine import sample_orders


def test_autonomous_changes_and_failed_plan_clear_manifest():
    state = {}
    df = sample_orders()
    assert replan(state, df, [])
    assert not replan(state, df, [])
    df.loc[0, 'deadline_days'] = 3
    assert replan(state, df, [])
    assert all(p.eta_days <= 3 for p in state['result']['selected'] if 'KK001' in p.ids)
    assert replan(state, df, ['Demo Consolidated Freight'])
    assert all(p.provider != 'Demo Consolidated Freight' for p in state['result']['selected'])
    replan(state, df, PROVIDERS)
    assert state['result'] is None and state['error']
    assert state['history'][-1]['status'] == 'Blocked'
    replan(state, df, [])
    assert state['result'] and not state['error']
    assert len(state['history']) == 5


@pytest.mark.parametrize('column,value', [('origin',None), ('order_id',' '), ('weight_kg',float('inf')), ('deadline_days',1.5)])
def test_invalid_import(column, value):
    df = sample_orders().astype(object); df.loc[0,column] = value
    with pytest.raises(ValueError): normalize(df)


def test_csv_roundtrip_and_simulation_labels():
    df = normalize(pd.read_csv(io.StringIO(sample_orders().to_csv(index=False))))
    state = {}; replan(state, df, [])
    table = pd.read_csv(io.StringIO(manifest(state['result']).to_csv(index=False)))
    assert table['Data status'].str.contains('SIMULATED / FICTIONAL').all()
    assert table['Simulated cost (RM)'].sum() == pytest.approx(state['result']['total'])
    assert sorted(', '.join(table.Orders).split(', ')) == sorted(df.order_id)


def test_streamlit_plan_and_automatic_availability_event():
    app = AppTest.from_file('../app.py', default_timeout=20).run()
    assert not app.exception
    next(b for b in app.button if b.label == 'Plan shipments').click().run()
    assert not app.exception
    assert len(app.metric) == 4
    app.multiselect[0].set_value(PROVIDERS).run()
    assert not app.exception
    assert app.error and len(app.metric) == 0
    app.multiselect[0].set_value([]).run()
    assert not app.exception and len(app.metric) == 4
