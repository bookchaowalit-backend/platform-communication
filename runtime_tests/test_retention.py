"""Terminal message content is cleared after the retention window; nothing else changes."""
import os
from uuid import uuid4

import psycopg
import pytest
from platform_backend_core import Database, MigrationRunner
from platform_backend_core.testing import temporary_database

from platform_communication.migrations import MIGRATIONS
from platform_communication.store import OutboxStore


@pytest.fixture
def database():
    dsn=os.environ.get('PLATFORM_TEST_DSN')
    if not dsn: pytest.skip('explicit disposable PostgreSQL DSN required')
    with temporary_database(dsn,prefix='ret_') as temp:
        MigrationRunner(temp.admin_dsn,namespace='communication').apply(MIGRATIONS)
        temp.grant_schema('public')
        # Production's runtime role has no DELETE; retention must not need it.
        with psycopg.connect(temp.admin_dsn) as admin:
            admin.execute(psycopg.sql.SQL('REVOKE DELETE ON ALL TABLES IN SCHEMA public FROM {}').format(psycopg.sql.Identifier(temp.runtime_role)))
        db=Database(temp.runtime_dsn)
        yield db
        db.close()

def _age(db,w,id,days,status):
    with db.transaction(w) as c:
        c.execute("UPDATE message_outbox SET status=%s,created_at=clock_timestamp()-%s*interval '1 day' WHERE id=%s",(status,days,id))

def test_old_terminal_content_is_cleared_and_the_rest_kept(database):
    db=database;s=OutboxStore(db);w=uuid4();other=uuid4()
    rows={}
    for name,status,days in [('delivered','delivered',31),('dead','dead',31),('suppressed','suppressed',31),
                             ('recent','delivered',29),('queued','queued',31),('uncertain','uncertain',31)]:
        rows[name]=s.create(w,name,'email','a@example.invalid','secret body '+name,'plain',subject='Subject '+name)['id']
        _age(db,w,rows[name],days,status)
    foreign=s.create(other,'foreign','email','b@example.invalid','foreign body','plain',subject='Foreign')['id']
    _age(db,other,foreign,31,'delivered')

    assert s.redact_terminal(w,older_than_days=30)==3
    for name in ('delivered','dead','suppressed'):
        row=s.get(w,rows[name])
        assert row['body']=='' and row['subject'] is None
        assert row['recipient']=='a@example.invalid'  # unsubscribe links in old emails still work
    for name in ('recent','queued','uncertain'):
        assert s.get(w,rows[name])['body']=='secret body '+name
    assert s.get(other,foreign)['body']=='foreign body'
    assert s.redact_terminal(w,older_than_days=30)==0  # idempotent

def test_retention_window_is_bounded(database):
    s=OutboxStore(database)
    for bad in (0,6,3651,'30',30.0,True):
        with pytest.raises(ValueError):s.redact_terminal(uuid4(),older_than_days=bad)
