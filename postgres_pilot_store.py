"""PostgreSQL implementation of the private pilot draft store.

Only server-verified OIDC subjects are accepted. No provider tokens or bookings
are stored here. Production TLS policy is enforced by pilot_api.configured_store.
"""
import hashlib
import json
import uuid

from psycopg_pool import ConnectionPool
from pilot_planning import evaluate as evaluate_plan, fingerprint as plan_fingerprint, manifest_csv

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
                    versions = db.execute('SELECT version FROM pilot_schema_versions').fetchall()
                    if not versions:
                        db.execute('INSERT INTO pilot_schema_versions (version) VALUES (1)')
                        versions = [(1,)]
                    if versions not in ([(1,)], [(2,)]):
                        raise RuntimeError('Unsupported pilot storage schema version.')
                    db.execute("ALTER TABLE pilot_jobs ADD COLUMN IF NOT EXISTS unavailable_json TEXT NOT NULL DEFAULT '[]'")
                    db.execute('''CREATE TABLE IF NOT EXISTS pilot_proposals (
                        proposal_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES pilot_jobs(job_id),
                        owner_sub TEXT NOT NULL, input_fingerprint TEXT NOT NULL,
                        result_json TEXT NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
                    db.execute('''CREATE TABLE IF NOT EXISTS pilot_audit (
                        event_id BIGSERIAL PRIMARY KEY, job_id TEXT NOT NULL REFERENCES pilot_jobs(job_id),
                        owner_sub TEXT NOT NULL, action TEXT NOT NULL, detail_json TEXT NOT NULL,
                        occurred_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
                    if versions == [(1,)]:
                        db.execute('''CREATE FUNCTION pilot_audit_no_change() RETURNS trigger LANGUAGE plpgsql AS
                            $$ BEGIN RAISE EXCEPTION 'Pilot audit events are immutable'; END $$''')
                        db.execute('''CREATE TRIGGER pilot_audit_no_change BEFORE UPDATE OR DELETE ON pilot_audit
                            FOR EACH ROW EXECUTE FUNCTION pilot_audit_no_change()''')
                        db.execute('UPDATE pilot_schema_versions SET version=2 WHERE version=1')
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

    @staticmethod
    def _plan_inputs(db, owner, job_id, lock=False):
        lock_sql = ' FOR UPDATE' if lock else ''
        row = db.execute('''SELECT orders_json,version,unavailable_json FROM pilot_jobs
                            WHERE job_id=%s AND owner_sub=%s''' + lock_sql, (job_id, owner)).fetchone()
        if row is None:
            raise PermissionError('Job unavailable.')
        quotes = db.execute('''SELECT quote_id,quote_json,version FROM pilot_quotes
                               WHERE job_id=%s AND owner_sub=%s ORDER BY quote_id''',
                            (job_id, owner)).fetchall()
        return row, quotes

    def set_availability(self, identity_token, job_id, unavailable, expected_version):
        owner = self.verifier.verify(identity_token)
        if (not isinstance(unavailable, list) or len(unavailable) > 50 or
                any(not isinstance(name, str) or not name.strip() or len(name) > 120 for name in unavailable) or
                len(set(unavailable)) != len(unavailable)):
            raise ValueError('Unavailable providers must be a unique list of provider names.')
        with self.pool.connection() as db:
            with db.transaction():
                (orders_json, version, previous), _ = self._plan_inputs(db, owner, job_id, lock=True)
                if version != expected_version:
                    raise ValueError('Job changed; reload before updating availability.')
                value = json.dumps(sorted(unavailable), separators=(',', ':'))
                if value != previous:
                    db.execute('''UPDATE pilot_jobs SET unavailable_json=%s,version=version+1
                                  WHERE job_id=%s AND owner_sub=%s''', (value, job_id, owner))
                    db.execute('''INSERT INTO pilot_audit (job_id,owner_sub,action,detail_json)
                                  VALUES (%s,%s,%s,%s)''',
                               (job_id, owner, 'AVAILABILITY_CHANGED', json.dumps({'unavailable': sorted(unavailable)})))
        return self.job_snapshot(identity_token, job_id)

    def availability(self, identity_token, job_id):
        owner = self.verifier.verify(identity_token)
        with self.pool.connection() as db:
            row, _ = self._plan_inputs(db, owner, job_id)
        return json.loads(row[2])

    def create_proposal(self, identity_token, job_id, idempotency_key=None):
        owner = self.verifier.verify(identity_token)
        with self.pool.connection() as db:
            with db.transaction():
                (orders_json, version, unavailable_json), quote_rows = self._plan_inputs(db, owner, job_id, lock=True)
                current = plan_fingerprint(orders_json, quote_rows, unavailable_json, version)
                key = 'proposal:' + idempotency_key if idempotency_key else None
                prior = self._prior_request(db, owner, key, job_id + current)
                if prior:
                    existing = db.execute('''SELECT result_json,status,version,created_at FROM pilot_proposals
                                             WHERE proposal_id=%s AND job_id=%s AND owner_sub=%s''',
                                          (prior, job_id, owner)).fetchone()
                    if existing is None:
                        raise ValueError('Proposal changed; create a fresh proposal.')
                    return {'proposal_id': prior, 'approval_status': existing[1],
                            'version': existing[2], 'created_at': existing[3].isoformat(),
                            **json.loads(existing[0])}
                result = evaluate_plan(orders_json, quote_rows, unavailable_json)
                if result['status'] == 'NOT READY':
                    return result
                proposal_id = 'PPLAN-' + uuid.uuid4().hex.upper()
                db.execute('''INSERT INTO pilot_proposals
                              (proposal_id,job_id,owner_sub,input_fingerprint,result_json,status)
                              VALUES (%s,%s,%s,%s,%s,%s)''',
                           (proposal_id, job_id, owner, current, self._payload(result), 'PROPOSED'))
                self._record_request(db, owner, key, job_id + current, proposal_id)
                db.execute('''INSERT INTO pilot_audit (job_id,owner_sub,action,detail_json)
                              VALUES (%s,%s,%s,%s)''',
                           (job_id, owner, 'PLAN_PROPOSED', self._payload({
                               'proposal_id': proposal_id, 'quote_ids': [d['quote_id'] for d in result['decisions']],
                               'total_myr': result['total_myr'], 'booking': False})))
                return {'proposal_id': proposal_id, 'version': 1, 'approval_status': 'PROPOSED', **result}

    def list_proposals(self, identity_token, job_id):
        owner = self.verifier.verify(identity_token)
        with self.pool.connection() as db:
            self._plan_inputs(db, owner, job_id)
            rows = db.execute('''SELECT proposal_id,status,version,created_at FROM pilot_proposals
                                 WHERE job_id=%s AND owner_sub=%s ORDER BY created_at DESC,proposal_id DESC''',
                              (job_id, owner)).fetchall()
        return [{'proposal_id': row[0], 'approval_status': row[1], 'version': row[2],
                 'created_at': row[3].isoformat()} for row in rows]

    def proposal_snapshot(self, identity_token, job_id, proposal_id):
        owner = self.verifier.verify(identity_token)
        with self.pool.connection() as db:
            row = db.execute('''SELECT p.result_json,p.status,p.version,p.created_at FROM pilot_proposals p
                                JOIN pilot_jobs j ON j.job_id=p.job_id AND j.owner_sub=p.owner_sub
                                WHERE p.proposal_id=%s AND p.job_id=%s AND p.owner_sub=%s''',
                             (proposal_id, job_id, owner)).fetchone()
        if row is None:
            raise PermissionError('Proposal unavailable.')
        return {'proposal_id': proposal_id, 'approval_status': row[1], 'version': row[2],
                'created_at': row[3].isoformat(), **json.loads(row[0])}

    def approve_proposal(self, identity_token, job_id, proposal_id, expected_version):
        owner = self.verifier.verify(identity_token)
        with self.pool.connection() as db:
            with db.transaction():
                (orders_json, version, unavailable_json), quote_rows = self._plan_inputs(db, owner, job_id, lock=True)
                row = db.execute('''SELECT input_fingerprint,result_json,status,version FROM pilot_proposals
                                    WHERE proposal_id=%s AND job_id=%s AND owner_sub=%s FOR UPDATE''',
                                 (proposal_id, job_id, owner)).fetchone()
                if row is None:
                    raise PermissionError('Proposal unavailable.')
                old_hash, old_result, status, proposal_version = row
                if status != 'PROPOSED' or proposal_version != expected_version:
                    raise ValueError('Proposal changed or already approved; reload before approval.')
                current_hash = plan_fingerprint(orders_json, quote_rows, unavailable_json, version)
                if current_hash != old_hash:
                    raise ValueError('Inputs changed; create a fresh proposal.')
                current = evaluate_plan(orders_json, quote_rows, unavailable_json)
                if current['status'] == 'NOT READY' or self._payload(current) != old_result:
                    raise ValueError('Quotation eligibility changed; create a fresh proposal.')
                db.execute('''UPDATE pilot_proposals SET status='APPROVED',version=version+1
                              WHERE proposal_id=%s AND job_id=%s AND owner_sub=%s''',
                           (proposal_id, job_id, owner))
                db.execute('''INSERT INTO pilot_audit (job_id,owner_sub,action,detail_json)
                              VALUES (%s,%s,%s,%s)''',
                           (job_id, owner, 'PLAN_APPROVED', self._payload({
                               'proposal_id': proposal_id, 'quote_ids': [d['quote_id'] for d in current['decisions']],
                               'total_myr': current['total_myr'], 'booking': False})))
        return self.proposal_snapshot(identity_token, job_id, proposal_id)

    def approved_manifest(self, identity_token, job_id, proposal_id):
        owner = self.verifier.verify(identity_token)
        with self.pool.connection() as db:
            with db.transaction():
                (orders_json, version, unavailable_json), quote_rows = self._plan_inputs(db, owner, job_id, lock=True)
                row = db.execute('''SELECT input_fingerprint,result_json,status FROM pilot_proposals
                                    WHERE proposal_id=%s AND job_id=%s AND owner_sub=%s''',
                                 (proposal_id, job_id, owner)).fetchone()
                if row is None:
                    raise PermissionError('Proposal unavailable.')
                if row[2] != 'APPROVED':
                    raise ValueError('Approve the proposal before exporting a manifest.')
                if plan_fingerprint(orders_json, quote_rows, unavailable_json, version) != row[0]:
                    raise ValueError('Inputs changed; approved manifest is outdated.')
                current = evaluate_plan(orders_json, quote_rows, unavailable_json)
                if current['status'] == 'NOT READY' or self._payload(current) != row[1]:
                    raise ValueError('Quotation eligibility changed; approved manifest is outdated.')
        return manifest_csv(job_id, json.loads(orders_json), current)

    def audit_events(self, identity_token, job_id):
        owner = self.verifier.verify(identity_token)
        with self.pool.connection() as db:
            self._plan_inputs(db, owner, job_id)
            rows = db.execute('''SELECT event_id,action,detail_json,occurred_at FROM pilot_audit
                                 WHERE job_id=%s AND owner_sub=%s ORDER BY event_id''',
                              (job_id, owner)).fetchall()
        return [{'event_id': row[0], 'action': row[1], 'detail': json.loads(row[2]),
                 'occurred_at': row[3].isoformat()} for row in rows]
