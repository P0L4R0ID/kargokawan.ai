from unittest.mock import patch
from types import SimpleNamespace
from streamlit.testing.v1 import AppTest
import pytest
from demo_scenario import load_demo
from mixed_method import optimize,preview,approve

def test_demo_disruption_approval_and_isolation():
 orders,quotes=load_demo()
 before=optimize(orders,quotes,demo=True)
 assert before['status']=='READY' and before['baseline_myr']==80 and before['total_myr']==55
 assert before['claim'].startswith('SIMULATED DEMO')
 proposal=preview(orders,quotes,demo=True)
 after=optimize(orders,quotes,['Synthetic Lalamove example'],demo=True)
 assert after['total_myr']==80
 with pytest.raises(ValueError,match='fresh'): approve(proposal,orders,quotes,['Synthetic Lalamove example'],demo=True)
 assert approve(preview(orders,quotes,['Synthetic Lalamove example'],demo=True),orders,quotes,['Synthetic Lalamove example'],demo=True)['total_myr']==80
 assert optimize(orders,quotes)['status']=='NOT READY'

def test_solver_status_and_bad_fractional_solution():
 orders,quotes=load_demo()
 import numpy as np
 with patch('mixed_method.milp',return_value=SimpleNamespace(status=1,x=np.array([1,1,1,1,0]))):
  result=optimize(orders,quotes,demo=True)
  assert result['status']=='SOLVER LIMITED' and 'limit' in result['reason']
 with patch('mixed_method.milp',return_value=SimpleNamespace(status=0,x=np.array([.5,.5,.5,.5,0]))):
  assert optimize(orders,quotes,demo=True)['status']=='NOT READY'
 with patch('mixed_method.milp',return_value=SimpleNamespace(status=2,x=None)):
  assert optimize(orders,quotes,demo=True)['status']=='NOT READY'

def test_demo_ui():
 app=AppTest.from_file('../app.py',default_timeout=20).run()
 next(b for b in app.button if b.label=='Load Demo Scenario').click().run()
 assert not app.exception
 assert any('SIMULATED DEMO' in x.body for x in app.error)
 next(b for b in app.button if b.label=='Preview demo plan').click().run()
 assert app.session_state['demo_preview']
 next(b for b in app.button if b.label=='Approve demo proposal').click().run()
 assert app.session_state['demo_approved']['total_myr']==55
 app.checkbox[0].check().run()
 assert app.session_state['demo_approved'] is None
 assert app.session_state['demo_unavailable']==['Synthetic Lalamove example']
