import pandas as pd
import pytest

from engine import sample_orders, validate, solve, agent_run, candidates, CITIES


def test_sample_covers_multiple_malaysian_regions():
    d = sample_orders()
    assert len(d) == 15
    assert {'Kuala Lumpur', 'Kota Kinabalu', 'Kuching', 'George Town', 'Johor Bahru'}.issubset(set(d.origin) | set(d.destination))
    assert validate(d).shape[0] == 15


def test_optimizer_covers_every_order_exactly_once_and_within_deadline():
    df = sample_orders()
    output = solve(df)
    covered = [oid for option in output['selected'] for oid in option.ids]
    assert sorted(covered) == sorted(df.order_id.tolist())
    deadlines = dict(zip(df.order_id, df.deadline_days))
    for option in output['selected']:
        assert all(option.eta_days <= deadlines[oid] for oid in option.ids)
    assert output['total'] <= output['baseline_cost'] + 0.01


def test_replanning_after_deadline_change():
    df = sample_orders()
    before = solve(df)
    df.loc[df.order_id == 'KK001', 'deadline_days'] = 3
    after = solve(df)
    assert after['total'] >= before['total']
    assert all(opt.eta_days <= 3 for opt in after['selected'] if 'KK001' in opt.ids)


def test_replanning_when_consolidation_unavailable():
    df = sample_orders()
    output = solve(df, disabled=['Demo Consolidated Freight'])
    assert not any(o.provider == 'Demo Consolidated Freight' for o in output['selected'])


def test_invalid_destination_rejected():
    df = sample_orders()
    df.loc[0, 'destination'] = 'Atlantis'
    with pytest.raises(ValueError, match='Unsupported destination'):
        validate(df)


def test_duplicate_orders_rejected():
    df = sample_orders()
    df.loc[1, 'order_id'] = df.loc[0, 'order_id']
    with pytest.raises(ValueError, match='unique'):
        validate(df)


def test_grouping_never_mix_different_destinations():
    df = sample_orders()
    location_by_order = {str(r.order_id): (r.origin, r.destination) for r in df.itertuples()}
    for plan in candidates(df):
        if len(plan.ids) > 1:
            assert len({location_by_order[oid] for oid in plan.ids}) == 1


def test_agent_run_produces_trace():
    result, trace = agent_run(sample_orders())
    assert result['selected']
    assert any('Optimisation tool' in step for step in trace)
