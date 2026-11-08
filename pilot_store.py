"""Isolated owner-scoped pilot data boundary; not connected to public Streamlit.

Every operation verifies a signed OIDC identity token on the server. The caller
cannot choose an owner by passing a job ID or user-supplied string.
"""
import json
import hashlib
import time
import sqlite3
import uuid
from pathlib import Path
from urllib import request
from urllib.parse import urlsplit
import jwt
from jwt import InvalidTokenError


class OperatorVerifier:
    def __init__(self, issuer, audience, operator_subject, jwks_url=None, jwks=None):
        if urlsplit(issuer).scheme != 'https' or not audience or not operator_subject:
            raise ValueError('OIDC issuer, audience and allowlisted operator subject are required.')
        if jwks is None and (not jwks_url or urlsplit(jwks_url).scheme != 'https'):
            raise ValueError('An HTTPS OIDC JWKS URL is required.')
        self.issuer = issuer
        self.audience = audience
        self.operator_subject = operator_subject
        self.jwks_url = jwks_url
        self.jwks = jwks
        self._jwks_until = 0
        self._cached_jwks = None

    def verify(self, token):
        if not isinstance(token, str) or not token:
            raise PermissionError('Authenticated operator identity is required.')
        try:
            header = jwt.get_unverified_header(token)
            if header.get('alg') != 'RS256' or not header.get('kid'):
                raise PermissionError('Unsupported identity signature.')
            if self.jwks is None:
                if time.monotonic() >= self._jwks_until:
                    with request.urlopen(self.jwks_url, timeout=5) as response:
                        document = response.read(65537)
                    if len(document) > 65536:
                        raise PermissionError('Identity key set is too large.')
                    self._cached_jwks = json.loads(document)
                    self._jwks_until = time.monotonic() + 300
                jwks = self._cached_jwks
            else:
                jwks = self.jwks
            matching = [key for key in jwks['keys'] if key.get('kid') == header['kid'] and key.get('kty') == 'RSA']
            if len(matching) != 1:
                raise PermissionError('Identity signing key is unavailable.')
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(matching[0]))
            claims = jwt.decode(token, public_key, algorithms=['RS256'], issuer=self.issuer,
                                audience=self.audience, options={'require': ['iss', 'aud', 'sub', 'iat', 'exp']}, leeway=30)
        except (InvalidTokenError, ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
            raise PermissionError('Operator identity could not be verified.') from None
        if claims['sub'] != self.operator_subject:
            raise PermissionError('Operator is not authorized.')
        return claims['sub']


class PilotStore:
    """Persist jobs and manual quote drafts only on an approved persistent mount."""
    def __init__(self, path, verifier, persistent_root='/var/data'):
        self.path = Path(path).resolve()
        root = Path(persistent_root).resolve()
        if self.path == root or root not in self.path.parents or not root.is_dir():
            raise ValueError('Pilot database must be under an existing persistent mount.')
        self.verifier = verifier
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS pilot_jobs (job_id TEXT PRIMARY KEY, owner_sub TEXT NOT NULL, orders_json TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1)')
            db.execute('CREATE TABLE IF NOT EXISTS pilot_quotes (quote_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, owner_sub TEXT NOT NULL, quote_json TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, FOREIGN KEY(job_id) REFERENCES pilot_jobs(job_id) ON DELETE CASCADE)')
            db.execute('CREATE TABLE IF NOT EXISTS pilot_requests (owner_sub TEXT NOT NULL, request_key TEXT NOT NULL, request_hash TEXT NOT NULL, response_id TEXT NOT NULL, PRIMARY KEY(owner_sub, request_key))')

    def _db(self):
        db = sqlite3.connect(self.path)
        self.path.chmod(0o600)
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @staticmethod
    def _payload(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

    @staticmethod
    def _prior_request(db, owner, key, payload):
        if not key:
            return None
        row = db.execute('SELECT request_hash,response_id FROM pilot_requests WHERE owner_sub=? AND request_key=?', (owner,key)).fetchone()
        if row:
            if row[0] != hashlib.sha256(payload.encode()).hexdigest():
                raise ValueError('Idempotency key was reused with different content.')
            return row[1]
        return None

    @staticmethod
    def _record_request(db, owner, key, payload, response_id):
        if key:
            db.execute('INSERT INTO pilot_requests VALUES (?,?,?,?)',
                       (owner,key,hashlib.sha256(payload.encode()).hexdigest(),response_id))

    def create_job(self, identity_token, orders, idempotency_key=None):
        owner = self.verifier.verify(identity_token)
        if not isinstance(orders, list) or not all(isinstance(row, dict) for row in orders):
            raise ValueError('Orders must be a list of records.')
        job_id = 'PILOT-' + uuid.uuid4().hex.upper()
        payload = self._payload(orders)
        key = 'job:' + idempotency_key if idempotency_key else None
        with self._db() as db:
            prior=self._prior_request(db,owner,key,payload)
            if prior: return prior
            db.execute('INSERT INTO pilot_jobs (job_id,owner_sub,orders_json) VALUES (?, ?, ?)', (job_id, owner, payload))
            self._record_request(db,owner,key,payload,job_id)
        return job_id

    def list_jobs(self, identity_token):
        owner = self.verifier.verify(identity_token)
        with self._db() as db:
            return [row[0] for row in db.execute('SELECT job_id FROM pilot_jobs WHERE owner_sub=? ORDER BY job_id', (owner,))]

    def get_job(self, identity_token, job_id):
        return self.job_snapshot(identity_token, job_id)['orders']

    def job_snapshot(self, identity_token, job_id):
        owner = self.verifier.verify(identity_token)
        with self._db() as db:
            row = db.execute('SELECT orders_json,version FROM pilot_jobs WHERE job_id=? AND owner_sub=?', (job_id, owner)).fetchone()
        if row is None:
            raise PermissionError('Job unavailable.')
        return {'orders':json.loads(row[0]),'version':row[1]}

    def replace_job(self, identity_token, job_id, orders, expected_version=None):
        owner = self.verifier.verify(identity_token)
        self.job_snapshot(identity_token,job_id)
        if not isinstance(orders, list) or not all(isinstance(row, dict) for row in orders):
            raise ValueError('Orders must be a list of records.')
        with self._db() as db:
            cursor = db.execute('UPDATE pilot_jobs SET orders_json=?,version=version+1 WHERE job_id=? AND owner_sub=? AND (? IS NULL OR version=?)',
                                (self._payload(orders), job_id, owner, expected_version, expected_version))
            if cursor.rowcount != 1:
                raise ValueError('Job changed; reload before updating.')
            db.execute('DELETE FROM pilot_requests WHERE owner_sub=? AND response_id IN (SELECT quote_id FROM pilot_quotes WHERE job_id=? AND owner_sub=?)',
                       (owner,job_id,owner))
            db.execute('DELETE FROM pilot_quotes WHERE job_id=? AND owner_sub=?', (job_id, owner))

    def create_quote(self, identity_token, job_id, quote, idempotency_key=None):
        owner = self.verifier.verify(identity_token)
        self.get_job(identity_token, job_id)
        if not isinstance(quote, dict) or quote.get('source_class') not in ('PUBLIC_REFERENCE', 'USER_IMPORTED_UNVERIFIED'):
            raise ValueError('Only unverified manual or public-reference quote drafts may be saved.')
        quote_id = 'PQUOTE-' + uuid.uuid4().hex.upper()
        payload = self._payload(quote)
        key = 'quote:' + idempotency_key if idempotency_key else None
        with self._db() as db:
            prior=self._prior_request(db,owner,key,job_id+payload)
            if prior: return prior
            db.execute('INSERT INTO pilot_quotes (quote_id,job_id,owner_sub,quote_json) VALUES (?, ?, ?, ?)',
                       (quote_id, job_id, owner, payload))
            self._record_request(db,owner,key,job_id+payload,quote_id)
        return quote_id

    def list_quotes(self, identity_token, job_id):
        owner = self.verifier.verify(identity_token)
        self.get_job(identity_token, job_id)
        with self._db() as db:
            return [row[0] for row in db.execute('SELECT quote_id FROM pilot_quotes WHERE job_id=? AND owner_sub=? ORDER BY quote_id', (job_id, owner))]

    def get_quote(self, identity_token, job_id, quote_id):
        return self.quote_snapshot(identity_token,job_id,quote_id)['quote']

    def quote_snapshot(self, identity_token, job_id, quote_id):
        owner = self.verifier.verify(identity_token)
        self.get_job(identity_token, job_id)
        with self._db() as db:
            row = db.execute('SELECT quote_json,version FROM pilot_quotes WHERE quote_id=? AND job_id=? AND owner_sub=?',
                             (quote_id, job_id, owner)).fetchone()
        if row is None:
            raise PermissionError('Quote unavailable.')
        return {'quote':json.loads(row[0]),'version':row[1]}

    def replace_quote(self, identity_token, job_id, quote_id, quote, expected_version=None):
        owner = self.verifier.verify(identity_token)
        self.quote_snapshot(identity_token,job_id,quote_id)
        if not isinstance(quote, dict) or quote.get('source_class') not in ('PUBLIC_REFERENCE', 'USER_IMPORTED_UNVERIFIED'):
            raise ValueError('Only unverified manual or public-reference quote drafts may be saved.')
        with self._db() as db:
            cursor = db.execute('UPDATE pilot_quotes SET quote_json=?,version=version+1 WHERE quote_id=? AND job_id=? AND owner_sub=? AND (? IS NULL OR version=?)',
                                (self._payload(quote), quote_id, job_id, owner, expected_version, expected_version))
            if cursor.rowcount != 1:
                raise ValueError('Quote changed; reload before updating.')

    def delete_quote(self, identity_token, job_id, quote_id):
        owner = self.verifier.verify(identity_token)
        self.get_job(identity_token, job_id)
        with self._db() as db:
            cursor = db.execute('DELETE FROM pilot_quotes WHERE quote_id=? AND job_id=? AND owner_sub=?',
                                (quote_id, job_id, owner))
            if cursor.rowcount != 1:
                raise PermissionError('Quote unavailable.')
