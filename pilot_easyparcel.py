"""Restricted pilot OAuth and one read-only fictional Sandbox rate check.

All credentials and provider tokens stay in the Render process/PostgreSQL. This
module never submits a shipment, books, cancels, pays or dispatches anything.
"""
import json
import os
import time
from urllib import request

from cryptography.fernet import Fernet, InvalidToken

from easyparcel_openapi import ProviderRateLimited, request_standard

BACKEND_ORIGIN = 'https://kargokawan-oauth.onrender.com'
CALLBACK = BACKEND_ORIGIN + '/oauth/easyparcel/callback'
AUTH_HOSTS = {'api':'https://api.easyparcel.com/oauth/login',
              'developer':'https://developer.easyparcel.com/oauth/login'}


def configuration(env=None):
    env = os.environ if env is None else env
    if env.get('EASYPARCEL_OAUTH_ENABLED') != '1':
        return None
    names = ('EASYPARCEL_OAUTH_CLIENT_ID','EASYPARCEL_OAUTH_CLIENT_SECRET',
             'EASYPARCEL_OAUTH_FERNET_KEY')
    if any(not env.get(name) for name in names) or env.get('EASYPARCEL_OAUTH_REDIRECT_URI') != CALLBACK:
        return None
    try:
        Fernet(env['EASYPARCEL_OAUTH_FERNET_KEY'].encode())
    except (ValueError, TypeError):
        return None
    return {name:env[name] for name in names} | {'EASYPARCEL_OAUTH_REDIRECT_URI':CALLBACK}


def save_authorization(store, owner, config, token, now=None, preserve_environment=False,
                       expected_ciphertext=None):
    """Validate lifetime and encrypt before any database write."""
    now = int(time.time() if now is None else now)
    try:
        lifetime = int(token['expires_in'])
        refresh_lifetime = int(token['refresh_token_expires_in'])
    except (KeyError, TypeError, ValueError):
        raise ValueError('Provider token lifetime was not supplied.') from None
    if (token.get('token_type','').lower() != 'bearer' or not token.get('access_token')
            or not token.get('refresh_token') or lifetime <= 60 or refresh_lifetime <= lifetime):
        raise ValueError('Provider token response is incomplete.')
    ciphertext = Fernet(config['EASYPARCEL_OAUTH_FERNET_KEY'].encode()).encrypt(
        json.dumps(token, separators=(',', ':')).encode())
    store.easyparcel_save_tokens(owner, ciphertext, now + lifetime, now + refresh_lifetime,
                                 now=now, preserve_environment=preserve_environment,
                                 expected_ciphertext=expected_ciphertext)


SAMPLE_ORDER = {'order_id':'FICTIONAL-SANDBOX-1', 'origin_postcode':'10150',
                'destination_postcode':'11950', 'weight_kg':1.5,
                'width_cm':5, 'length_cm':5, 'height_cm':5}
SAMPLE_CODES = {'FICTIONAL-SANDBOX-1':{'sender':'MY-07','receiver':'MY-07'}}


class PilotEasyParcelService:
    def __init__(self, store, config, transport=None, token_transport=None, clock=None):
        self.store = store
        self.config = config
        self.transport = transport or request.urlopen
        self.token_transport = token_transport
        self.clock = clock or time.time

    def _access_token(self, identity_token):
        record = self.store.easyparcel_token_record(identity_token)
        if record is None:
            raise ValueError('EasyParcel account is not connected.')
        try:
            token = json.loads(Fernet(self.config['EASYPARCEL_OAUTH_FERNET_KEY'].encode()).decrypt(record['ciphertext']))
        except (InvalidToken, UnicodeError, ValueError):
            raise ValueError('Stored EasyParcel authorization is unreadable; reconnect.') from None
        now = int(self.clock())
        if record['access_expires_at'] <= now + 60:
            if not token.get('refresh_token') or not record['refresh_expires_at'] or record['refresh_expires_at'] <= now + 60:
                raise ValueError('EasyParcel authorization expired; reconnect.')
            from oauth_callback import refresh_token
            try:
                refreshed = refresh_token(self.config, token['refresh_token'], self.token_transport)
            except Exception:
                raise ValueError('EasyParcel token refresh failed; reconnect.') from None
            if 'refresh_token' not in refreshed:
                refreshed['refresh_token'] = token['refresh_token']
                refreshed['refresh_token_expires_in'] = record['refresh_expires_at'] - now
            save_authorization(self.store, self.store.verifier.verify(identity_token),
                               self.config, refreshed, now, preserve_environment=True,
                               expected_ciphertext=record['ciphertext'])
            token = refreshed
        return token['access_token']

    def quote(self, identity_token, job_id, orders, subdivisions, request_key):
        raise ValueError('Private-job rate checks remain disabled during the first fictional Sandbox test.')

    def quote_sample(self, identity_token):
        # Verify ownership and existing connection before consuming rate quota.
        connection = self.store.easyparcel_connection(identity_token)
        if connection['status'] != 'CONNECTED':
            raise ValueError('EasyParcel account is not connected.')
        if connection['environment'] == 'Live':
            raise ValueError('Connected account is Live; Sandbox test is blocked.')
        access_token = self._access_token(identity_token)
        self.store.easyparcel_reserve_rate_check(identity_token, now=int(self.clock()))
        try:
            result = request_standard(access_token, [SAMPLE_ORDER], SAMPLE_CODES,
                                      transport=self.transport, timeout=12)
        except ProviderRateLimited as exc:
            if exc.provider_environment_evidence in ('Sandbox','Live'):
                self.store.easyparcel_update_environment(identity_token, exc.provider_environment_evidence)
            raise
        evidence = result.get('provider_environment_evidence')
        if evidence in ('Sandbox','Live'):
            self.store.easyparcel_update_environment(identity_token, evidence)
            result['environment'] = evidence
            for item in result['observations']:
                item['environment'] = evidence
        result['sample_input'] = 'FICTIONAL PDF EXAMPLE — no customer data'
        return result
