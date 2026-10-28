from platform_backend_core import Migration

MIGRATIONS=[Migration('0001',"""
CREATE TABLE message_outbox(workspace_id uuid NOT NULL,id uuid NOT NULL,event_key text NOT NULL,fingerprint text NOT NULL,channel text NOT NULL,recipient text NOT NULL,body text NOT NULL,template text NOT NULL,status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','leased','sending','delivered','dead','uncertain')),attempts integer NOT NULL DEFAULT 0,max_attempts integer NOT NULL CHECK(max_attempts BETWEEN 1 AND 10),run_at timestamptz NOT NULL DEFAULT clock_timestamp(),lease_token uuid,lease_until timestamptz,provider_id text,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(workspace_id,id),UNIQUE(workspace_id,event_key));
CREATE INDEX ON message_outbox(workspace_id,status,run_at,id);
CREATE INDEX ON message_outbox(workspace_id,created_at,id);
ALTER TABLE message_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE message_outbox FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace ON message_outbox USING(workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid) WITH CHECK(workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid);
""")]
# BOO-150 accepted policy: opt-out store (hashed addresses only), suppressed status, email subject.
MIGRATIONS.append(Migration('0002',"""
ALTER TABLE message_outbox DROP CONSTRAINT message_outbox_status_check;
ALTER TABLE message_outbox ADD CONSTRAINT message_outbox_status_check CHECK(status IN ('queued','leased','sending','delivered','dead','uncertain','suppressed'));
ALTER TABLE message_outbox ADD COLUMN subject text CHECK(subject IS NULL OR length(subject) BETWEEN 1 AND 200);
CREATE TABLE message_opt_out(workspace_id uuid NOT NULL,channel text NOT NULL CHECK(channel IN ('*','email','sms','push','telegram')),recipient_hash text NOT NULL,source text NOT NULL,event_id text NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(workspace_id,channel,recipient_hash),UNIQUE(workspace_id,event_id));
ALTER TABLE message_opt_out ENABLE ROW LEVEL SECURITY;
ALTER TABLE message_opt_out FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace ON message_opt_out USING(workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid) WITH CHECK(workspace_id=nullif(current_setting('app.workspace_id',true),'')::uuid);
"""))
