from demo_storage import demo_job_path

def test_session_scoped_demo_jobs(tmp_path):
    first={};second={}
    a=demo_job_path(first,tmp_path)
    assert demo_job_path(first,tmp_path)==a
    assert demo_job_path(second,tmp_path)!=a
    assert a.parent==tmp_path and a.name.startswith('demo_jobs_')

def test_untrusted_nonce_is_replaced(tmp_path):
    state={'demo_job_nonce':'../another-user'}
    path=demo_job_path(state,tmp_path)
    assert path.parent==tmp_path and '..' not in path.name
