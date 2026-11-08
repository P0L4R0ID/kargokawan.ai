"""Deployment requirements must include Streamlit's optional OIDC runtime."""
from importlib import import_module
from importlib.metadata import requires


def test_streamlit_oidc_dependencies_are_importable():
    dependencies = requires('streamlit') or []
    assert any('Authlib' in item and 'extra == "auth"' in item for item in dependencies)
    import_module('authlib')
    import_module('httpx')
