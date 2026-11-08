"""PostgreSQL implementation of the private pilot draft store.

Only server-verified OIDC subjects are accepted. No provider tokens or bookings
are stored here. Production TLS policy is enforced by pilot_api.configured_store.
"""
import hashlib
import json
import uuid

from psycopg_pool import ConnectionPool

PILOT_SCHEMA = 'kargokawan_pilot'


class PostgresPilotStore:
    def __init__(self, conninfo, verifier, *, conn_kwargs=None, min_size=0, max_size=3):
        self.verifier = verifier
        # Keep pilot tables outside Supabase's API-exposed public schema.
        kwargs = dict(conn_kwargs or {})
        kwargs['options'] = '-c search_path=' + PILOT_SCHEMA
        self.pool = ConnectionPool(conninfo, kwargs=kwargs, min_size=min_size,
                                   max_size=max_size, timeout=5, open=True)
        try:
            self.pool.wait(timeout=5)
            with self.pool.connection() as db:
                with db.transaction():
                    if db.execute('SELECT current_schema()').fetchone() != (PILOT_SCHEMA,):
                        raise RuntimeError('Private pilot database schema is not provisioned.')
                    # Serialise schema installation across backend workers.
                    db.execute('SELECT pg_advisory_xact_lock(49211077)')
                    db.execute('CREATE TABLE IF NOT EXISTS pilot_schema_versions (version INTEGER PRIMARY KEY)')
                    db.execute('''CREATE TABLE IF NOT EXISTS pilot_jobs (
                        job_id TEXT PRIMARY KEY, owner_sub TEXT NOT NULL,
                        orders_json TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1)''')
                    db.execute('''CREATE TABLE IF NOT EXISTS pilot_quotes (
                        quote_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES pilot_jobs(job_id) ON DELETE CASCADE,
                        owner_sub TEXT NOT NULL, quote_json TEXT NOT NULL,
                        version INTEGER NOT NULL DEFAULT 1)''')
                    db.execute('''CREATE TABLE IF NOT EXISTS pilot_requests (
                        owner_sub TEXT NOT NULL, request_key TEXT NOT NULL,
                        request_hash TEXT NOT NULL, response_id TEXT NOT NULL,
                        PRIMARY KEY(owner_sub, request_key))''')
                    db.execute('INSERT INTO pilot_schema_versions (version) VALUES (1) ON CONFLICT DO NOTHING')
                    versions = db.execute('SELECT version FROM pilot_schema_versions').fetchall()
                    if versions != [(1,)]:
                        raise RuntimeError('Unsupported pilot storage schema version.')
        except Exception:
            self.pool.close()
            raise

    def health(self):
        with self.pool.connection() as db:
            db.execute('SELECT 1').fetchone()

    @staticmethod
    def _payload(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

    @staticmethod
    def _prior_request(db, owner, key, payload):
        if not key:
            return None
        # Transaction-scoped lock makes concurrent retries exactly-once.
        db.execute('SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s))', (owner, key))
        row = db.execute('SELECT request_hash,response_id FROM pilot_requests WHERE owner_sub=%s AND request_key=%s',
                         (owner, key)).fetchone()
        if row:
            if row[0] != hashlib.sha256(payload.encode()).hexdigest():
                raise ValueError('Idempotency key was reused with different content.')
            return row[1]
        return None

    @staticmethod
    def _record_request(db, owner, key, payload, response_id):
        if key:
            db.execute('INSERT INTO pilot_requests VALUES (%s,%s,%s,%s)',
                       (owner, key, hashlib.sha256(payload.encode()).hexdigest(), response_id))

    def create_job(self, identity_token, orders, idempotency_key=None):
        owner = self.verifier.verify(identity_token)
        if not isinstance(orders, list) or not all(isinstance(row, dict) for row in orders):
            raise ValueError('Orders must be a list of records.')
        payload = self._payload(orders)
        key = 'job:' + idempotency_key if idempotency_key else None
        with self.pool.connection() as db:
            with db.transaction():
                prior = self._prior_request(db, owner, key, payload)
                if prior:
                    return prior
                job_id = 'PILOT-' + uuid.uuid4().hex.upper()
                db.execute('INSERT INTO pilot_jobs (job_id,owner_sub,orders_json) VALUES (%s,%s,%s)',
                           (job_id, owner, payload))
                self._record_request(db, owner, key, payload, job_id)
        return job_id

    def list_jobs(self, identity_token):
        owner = self.verifier.verify(identity_token)
        with self.pool.connection() as db:
            return [row[0] for row in db.execute('SELECT job_id FROM pilot_jobs WHERE owner_sub=%s ORDER BY job_id', (owner,))]

    def get_job(self, identity_token, job_id):
        return self.job_snapshot(identity_token, job_id)['orders']

    def job_snapshot(self, identity_token, job_id):
        owner = self.verifier.verify(identity_token)
        with self.pool.connection() as db:
            row = db.execute('SELECT orders_json,version FROM pilot_jobs WHERE job_id=%s AND owner_sub=%s',
                             (job_id, owner)).fetchone()
        if row is None:
            raise PermissionError('Job unavailable.')
        return {'orders': json.loads(row[0]), 'version': row[1]}

    def replace_job(self, identity_token, job_id, orders, expected_version=None):
        owner = self.verifier.verify(identity_token)
        if not isinstance(orders, list) or not all(isinstance(row, dict) for row in orders):
            raise ValueError('Orders must be a list of records.')
        with self.pool.connection() as db:
            with db.transaction():
                row = db.execute('SELECT version FROM pilot_jobs WHERE job_id=%s AND owner_sub=%s FOR UPDATE',
                                 (job_id, owner)).fetchone()
                if row is None:
                    raise PermissionError('Job unavailable.')
                if expected_version is not None and row[0] != expected_version:
                    raise ValueError('Job changed; reload before updating.')
                db.execute('UPDATE pilot_jobs SET orders_json=%s,version=version+1 WHERE job_id=%s AND owner_sub=%s',
                           (self._payload(orders), job_id, owner))
                db.execute('''DELETE FROM pilot_requests WHERE owner_sub=%s AND response_id IN
                           (SELECT quote_id FROM pilot_quotes WHERE job_id=%s AND owner_sub=%s)''',
                           (owner, job_id, owner))
                db.execute('DELETE FROM pilot_quotes WHERE job_id=%s AND owner_sub=%s', (job_id, owner))

    def create_quote(self, identity_token, job_id, quote, idempotency_key=None):
        owner = self.verifier.verify(identity_token)
        if not isinstance(quote, dict) or quote.get('source_class') not in ('PUBLIC_REFERENCE', 'USER_IMPORTED_UNVERIFIED'):
            raise ValueError('Only unverified manual or public-reference quote drafts may be saved.')
        payload = self._payload(quote)
        key = 'quote:' + idempotency_key if idempotency_key else None
        with self.pool.connection() as db:
            with db.transaction():
                # Order edits and quote writes cannot race past the quote invalidation.
                row = db.execute('SELECT 1 FROM pilot_jobs WHERE job_id=%s AND owner_sub=%s FOR UPDATE',
                                 (job_id, owner)).fetchone()
                if row is None:
                    raise PermissionError('Job unavailable.')
                prior = self._prior_request(db, owner, key, job_id + payload)
                if prior:
                    return prior
                quote_id = 'PQUOTE-' + uuid.uuid4().hex.upper()
                db.execute('INSERT INTO pilot_quotes (quote_id,job_id,owner_sub,quote_json) VALUES (%s,%s,%s,%s)',
                           (quote_id, job_id, owner, payload))
                self._record_request(db, owner, key, job_id + payload, quote_id)
        return quote_id

    def list_quotes(self, identity_token, job_id):
        owner = self.verifier.verify(identity_token)
        with self.pool.connection() as db:
            if db.execute('SELECT 1 FROM pilot_jobs WHERE job_id=%s AND owner_sub=%s', (job_id, owner)).fetchone() is None:
                raise PermissionError('Job unavailable.')
            return [row[0] for row in db.execute('SELECT quote_id FROM pilot_quotes WHERE job_id=%s AND owner_sub=%s ORDER BY quote_id',
                                                 (job_id, owner))]

    def get_quote(self, identity_token, job_id, quote_id):
        return self.quote_snapshot(identity_token, job_id, quote_id)['quote']

    def quote_snapshot(self, identity_token, job_id, quote_id):
        owner = self.verifier.verify(identity_token)
        with self.pool.connection() as db:
            row = db.execute('''SELECT quote_json,version FROM pilot_quotes WHERE
                              quote_id=%s AND job_id=%s AND owner_sub=%s''',
                             (quote_id, job_id, owner)).fetchone()
        if row is None:
            raise PermissionError('Quote unavailable.')
        return {'quote': json.loads(row[0]), 'version': row[1]}

    def replace_quote(self, identity_token, job_id, quote_id, quote, expected_version=None):
        owner = self.verifier.verify(identity_token)
        if not isinstance(quote, dict) or quote.get('source_class') not in ('PUBLIC_REFERENCE', 'USER_IMPORTED_UNVERIFIED'):
            raise ValueError('Only unverified manual or public-reference quote drafts may be saved.')
        with self.pool.connection() as db:
            with db.transaction():
                job = db.execute('SELECT 1 FROM pilot_jobs WHERE job_id=%s AND owner_sub=%s FOR UPDATE',
                                 (job_id, owner)).fetchone()
                if job is None:
                    raise PermissionError('Job unavailable.')
                row = db.execute('''SELECT version FROM pilot_quotes WHERE quote_id=%s AND job_id=%s
                                    AND owner_sub=%s FOR UPDATE''', (quote_id, job_id, owner)).fetchone()
                if row is None:
                    raise PermissionError('Quote unavailable.')
                if expected_version is not None and row[0] != expected_version:
                    raise ValueError('Quote changed; reload before updating.')
                db.execute('UPDATE pilot_quotes SET quote_json=%s,version=version+1 WHERE quote_id=%s AND job_id=%s AND owner_sub=%s',
                           (self._payload(quote), quote_id, job_id, owner))

    def delete_quote(self, identity_token, job_id, quote_id):
        owner = self.verifier.verify(identity_token)
        with self.pool.connection() as db:
            with db.transaction():
                row = db.execute('SELECT 1 FROM pilot_jobs WHERE job_id=%s AND owner_sub=%s FOR UPDATE',
                                 (job_id, owner)).fetchone()
                if row is None:
                    raise PermissionError('Job unavailable.')
                deleted = db.execute('DELETE FROM pilot_quotes WHERE quote_id=%s AND job_id=%s AND owner_sub=%s RETURNING quote_id',
                                     (quote_id, job_id, owner)).fetchone()
                if deleted is None:
                    raise PermissionError('Quote unavailable.')
                db.execute('DELETE FROM pilot_requests WHERE owner_sub=%s AND response_id=%s', (owner, quote_id))
