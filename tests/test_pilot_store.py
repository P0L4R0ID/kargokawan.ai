import base64
import time
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pilot_store import OperatorVerifier, PilotStore


def identities():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_numbers()
    b64 = lambda number: base64.urlsafe_b64encode(number.to_bytes((number.bit_length() + 7) // 8, 'big')).rstrip(b'=').decode()
    jwks = {'keys': [{'kty': 'RSA', 'kid': 'pilot-key', 'n': b64(public.n), 'e': b64(public.e)}]}
    def token(subject, **overrides):
        claims = {'iss': 'https://identity.example', 'aud': 'kargokawan-pilot', 'sub': subject,
                  'iat': int(time.time()), 'exp': int(time.time()) + 300}
        claims.update(overrides)
        return jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'pilot-key'})
    def verifier(subject):
        return OperatorVerifier('https://identity.example', 'kargokawan-pilot', subject, jwks=jwks)
    return token, verifier


def test_verified_identity_and_rejected_claims():
    token, verifier = identities()
    with pytest.raises(ValueError):
        OperatorVerifier('http://identity.example', 'kargokawan-pilot', 'operator-1', jwks={'keys': []})
    operator = verifier('operator-1')
    assert operator.verify(token('operator-1')) == 'operator-1'
    for bad in ('', token('other'), token('operator-1', aud='wrong'),
                token('operator-1', exp=int(time.time()) - 100), token('operator-1') + 'x'):
        with pytest.raises(PermissionError): operator.verify(bad)


def test_owner_scoping_every_read_and_mutation(tmp_path):
    token, verifier = identities()
    a = token('operator-1')
    b = token('operator-2')
    db_path = tmp_path / 'pilot.sqlite'
    first = PilotStore(db_path, verifier('operator-1'), tmp_path)
    second = PilotStore(db_path, verifier('operator-2'), tmp_path)
    job = first.create_job(a, [{'order_id': 'SYNTHETIC-1'}])
    assert first.get_job(a, job)[0]['order_id'] == 'SYNTHETIC-1'
    assert first.list_jobs(a) == [job]
    assert second.list_jobs(b) == []
    quote = first.create_quote(a, job, {'source_class': 'USER_IMPORTED_UNVERIFIED', 'note': 'synthetic test'})
    assert first.list_quotes(a, job) == [quote]
    assert first.get_quote(a, job, quote)['note'] == 'synthetic test'
    for operation in (lambda: second.get_job(b, job),
                      lambda: second.replace_job(b, job, []),
                      lambda: second.create_quote(b, job, {'source_class': 'PUBLIC_REFERENCE'}),
                      lambda: second.list_quotes(b, job),
                      lambda: second.get_quote(b, job, quote),
                      lambda: second.replace_quote(b, job, quote, {'source_class': 'PUBLIC_REFERENCE'}),
                      lambda: second.delete_quote(b, job, quote),
                      lambda: first.get_job(b, job)):
        with pytest.raises(PermissionError): operation()
    assert first.get_quote(a, job, quote)['note'] == 'synthetic test'
    first.replace_quote(a, job, quote, {'source_class': 'PUBLIC_REFERENCE'})
    assert first.get_quote(a, job, quote)['source_class'] == 'PUBLIC_REFERENCE'
    first.replace_job(a, job, [{'order_id': 'SYNTHETIC-2'}])
    assert first.list_quotes(a, job) == []
    with pytest.raises(PermissionError): first.get_quote(a, job, quote)


def test_store_requires_persistent_mount_and_unverified_provenance(tmp_path):
    token, verifier = identities()
    with pytest.raises(ValueError, match='persistent mount'):
        PilotStore(tmp_path / 'pilot.sqlite', verifier('operator-1'), tmp_path / 'missing')
    store = PilotStore(tmp_path / 'pilot.sqlite', verifier('operator-1'), tmp_path)
    job = store.create_job(token('operator-1'), [])
    for source in ('SYNTHETIC', 'LIVE_AUTHENTICATED', None):
        with pytest.raises(ValueError): store.create_quote(token('operator-1'), job, {'source_class': source})
    with pytest.raises(PermissionError): store.create_job('', [])
