from pathlib import Path
from streamlit.testing.v1 import AppTest
from demo_scenario import load_demo
from mixed_method import optimize,preview,approve
from delivery_operations import JobStore
from tests.test_delivery_operations import order,quote
import pytest

def test_both_demos_and_synthetic_isolation():
 orders,quotes=load_demo()
 assert optimize(orders,quotes,demo=True)['total_myr']==55
 assert optimize(orders,quotes)['status']=='NOT READY'
 app=AppTest.from_file('../app.py',default_timeout=20).run()
 next(b for b in app.button if b.label=='Load Demo Scenario').click().run()
 assert not app.exception
 next(b for b in app.button if b.label=='Load synthetic nationwide intake sample').click().run()
 assert not app.exception and len(app.session_state['ops_sample'])==15
 assert not any(b.label=='Create delivery job from approved quote plan' for b in app.button)

def test_job_requires_second_approval_and_disruption(tmp_path):
 store=JobStore(tmp_path/'jobs.sqlite');q=quote();o=[order()]
 job=store.create(o);store.propose(job,o,[q])
 assert store.get(job)['state']=='READY_FOR_REVIEW'
 with pytest.raises(ValueError):store.manifest(job)
 store.approve(job,o,[q]);assert store.get(job)['state']=='APPROVED'
 with pytest.raises(ValueError):store.record_booking(job,'ref','track','evidence')
 with pytest.raises(ValueError):store.propose(job,o,[q],['EasyParcel Malaysia'])
 assert store.get(job)['state']=='APPROVED'
