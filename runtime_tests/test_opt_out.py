"""BOO-150 accepted policy: opt-out, email subject and the max_attempts default."""
import json
import os
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from platform_backend_core import Database, MigrationRunner
from platform_backend_core.testing import temporary_database
from test_http import auth

from platform_communication.adapters import (
    DeliveryError,
    ResendAdapter,
    TelegramAdapter,
)
from platform_communication.app import create_app
from platform_communication.migrations import MIGRATIONS
from platform_communication.store import OutboxStore
from platform_communication.worker import DeliveryWorker


@pytest.fixture
def database():
    dsn=os.environ.get('PLATFORM_TEST_DSN')
    if not dsn:pytest.skip('explicit disposable PostgreSQL DSN required')
    with temporary_database(dsn,prefix='optout_') as temp:
        MigrationRunner(temp.admin_dsn,namespace='communication').apply(MIGRATIONS)
        temp.grant_schema('public')
        db=Database(temp.runtime_dsn)
        yield db,temp
        db.close()


class Recording:
    configured=True
    def __init__(self):self.sent=[]
    def send(self,message):
        self.sent.append(message['id'])
        return 'provider-fixture'


def test_opted_out_recipient_is_suppressed_before_any_provider_call(database):
    db,_=database;s=OutboxStore(db);w=uuid4();adapter=Recording()
    assert s.record_opt_out(w,'email','Person@Example.invalid','email.list_unsubscribe','evt-1')=='created'
    row=s.create(w,'blocked','email','person@example.invalid','hi','plain')
    worker=DeliveryWorker(s,{'email':adapter})
    assert worker.run_one(w) is False
    stored=s.get(w,row['id'])
    assert stored['status']=='suppressed' and stored['attempts']==0
    assert adapter.sent==[]


def test_wildcard_opt_out_blocks_every_channel_and_other_recipients_still_send(database):
    db,_=database;s=OutboxStore(db);w=uuid4();adapter=Recording()
    s.record_opt_out(w,'*','+12025550123','owner.global','evt-global')
    blocked=s.create(w,'sms-blocked','sms','+12025550123','hi','plain')
    allowed=s.create(w,'email-ok','email','other@example.invalid','hi','plain')
    worker=DeliveryWorker(s,{'sms':adapter,'email':adapter})
    while worker.run_one(w):pass
    assert s.get(w,blocked['id'])['status']=='suppressed'
    assert s.get(w,allowed['id'])['status']=='delivered'
    assert adapter.sent==[allowed['id']]


def test_opt_out_for_another_channel_or_workspace_does_not_block(database):
    db,_=database;s=OutboxStore(db);w=uuid4()
    # '12345678901' is a valid recipient for both telegram and push.
    s.record_opt_out(w,'telegram','12345678901','owner.global','evt-tg')
    s.record_opt_out(uuid4(),'email','person@example.invalid','owner.global','evt-foreign')
    push=s.create(w,'push-ok','push','12345678901','hi','plain')
    email=s.create(w,'email-ok','email','person@example.invalid','hi','plain')
    worker=DeliveryWorker(s,{'push':Recording(),'email':Recording()})
    while worker.run_one(w):pass
    assert s.get(w,push['id'])['status']=='delivered'
    assert s.get(w,email['id'])['status']=='delivered'


def test_opt_out_recorded_after_claim_still_stops_the_send(database):
    db,_=database;s=OutboxStore(db);w=uuid4()
    row=s.create(w,'race','email','person@example.invalid','hi','plain')
    lease=s.claim(w)
    s.record_opt_out(w,'email','person@example.invalid','email.list_unsubscribe','evt-race')
    assert s.mark_sending(w,row['id'],lease['lease_token']) is False
    stored=s.get(w,row['id'])
    assert stored['status']=='suppressed' and stored['attempts']==0


def test_replayed_signal_changes_nothing_and_addresses_are_not_stored(database):
    db,temp=database;s=OutboxStore(db);w=uuid4()
    assert s.record_opt_out(w,'email','person@example.invalid','email.list_unsubscribe','evt-1')=='created'
    assert s.record_opt_out(w,'email','person@example.invalid','email.list_unsubscribe','evt-1')=='existing'
    assert s.record_opt_out(w,'email','person@example.invalid','owner.global','evt-2')=='existing'
    import psycopg
    with psycopg.connect(temp.admin_dsn) as admin:
        rows=admin.execute('SELECT * FROM message_opt_out').fetchall()
    assert len(rows)==1 and 'person@example.invalid' not in json.dumps(rows,default=str).lower()


def test_opt_out_input_is_validated(database):
    db,_=database;s=OutboxStore(db);w=uuid4()
    for args in [('fax','a@example.invalid','owner.global','e'),('email','not-an-email','owner.global','e'),
                 ('email','a@example.invalid','made.up','e'),('email','a@example.invalid','owner.global','')]:
        with pytest.raises(ValueError):s.record_opt_out(w,*args)


def test_opt_out_api_scope_replay_and_suppression(database):
    db,_=database;verifier,headers=auth();w=uuid4()
    with TestClient(create_app(db,verifier,adapters={'email':Recording()})) as c:
        body={'channel':'email','recipient':'person@example.invalid','source':'email.list_unsubscribe','event_id':'evt-api'}
        assert c.post('/v1/opt-outs',headers=headers('messages:write',w),json=body).status_code==403
        h=headers('opt-outs:write',w)
        first=c.post('/v1/opt-outs',headers=h,json=body)
        assert first.status_code==201 and first.json()=={'outcome':'created'}
        again=c.post('/v1/opt-outs',headers=h,json=body)
        assert again.status_code==200 and again.json()=={'outcome':'existing'}
        bad=c.post('/v1/opt-outs',headers=h,json=body|{'recipient':'SYNTHETIC_VALUE'})
        assert bad.status_code==422 and 'SYNTHETIC_VALUE' not in bad.text
        msg=c.post('/v1/messages',headers=headers('messages:write messages:read',w),json={'channel':'email','recipient':'person@example.invalid','body':'hi'})
        assert msg.status_code==202
        assert msg.json()['status']=='suppressed' and msg.json()['attempts']==0


def test_email_subject_is_sent_and_part_of_idempotency(database):
    db,_=database;s=OutboxStore(db);w=uuid4()
    row=s.create(w,'subj','email','a@example.invalid','hi','plain',subject='Your quote')
    assert row['subject']=='Your quote'
    from platform_communication.store import Conflict
    with pytest.raises(Conflict):s.create(w,'subj','email','a@example.invalid','hi','plain',subject='Changed')
    with pytest.raises(ValueError):s.create(w,'crlf','email','a@example.invalid','hi','plain',subject='a\r\nBcc: x@example.invalid')
    with pytest.raises(ValueError):s.create(w,'sms-subj','sms','+12025550123','hi','plain',subject='x')
    assert s.create(w,'nosubj','email','a@example.invalid','hi','plain')['subject'] is None


def test_resend_uses_message_subject_or_the_default():
    requests=[]
    def fixture(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'id':'fixture'})
    a=ResendAdapter('synthetic','from@example.invalid',transport=httpx.MockTransport(fixture))
    m={'id':UUID(int=1),'recipient':'a@example.invalid','body':'hi','template':'plain','subject':'Your quote'}
    a.send(m);a.send(m|{'subject':None})
    assert requests[0]['subject']=='Your quote' and requests[1]['subject']=='Notification'


@pytest.mark.parametrize('text,opt_out',[('Forbidden: bot was blocked by the user',True),('Forbidden: bot is not a member',False)])
def test_telegram_403_blocked_signal_is_detected(text,opt_out):
    transport=httpx.MockTransport(lambda request:httpx.Response(403,json={'ok':False,'description':text}))
    a=TelegramAdapter('123456:'+('x'*30),transport=transport)
    with pytest.raises(DeliveryError) as exc:a.send({'id':UUID(int=1),'recipient':'1234','body':'hi','template':'plain'})
    assert exc.value.outcome=='dead' and exc.value.opt_out is opt_out and str(exc.value)=='Delivery unavailable'


def test_default_max_attempts_matches_accepted_retry_policy(database):
    db,_=database;s=OutboxStore(db);w=uuid4()
    assert s.create(w,'default','email','a@example.invalid','hi','plain')['max_attempts']==3
    from platform_communication.app import Message
    assert Message(channel='email',recipient='a@example.invalid',body='hi').max_attempts==3


def test_telegram_blocked_by_user_records_opt_out(database):
    db,_=database;s=OutboxStore(db);w=uuid4()
    class Blocked:
        configured=True
        def send(self,message):raise DeliveryError('dead',opt_out=True)
    first=s.create(w,'tg-1','telegram','1234','hi','plain')
    DeliveryWorker(s,{'telegram':Blocked()}).run_one(w)
    assert s.get(w,first['id'])['status']=='dead'
    second=s.create(w,'tg-2','telegram','1234','hi','plain')
    adapter=Recording()
    DeliveryWorker(s,{'telegram':adapter}).run_one(w)
    assert s.get(w,second['id'])['status']=='suppressed' and adapter.sent==[]


def test_readiness_requires_forced_rls_on_the_opt_out_table(database):
    import psycopg
    db,temp=database;s=OutboxStore(db)
    assert s.ready() is True
    with psycopg.connect(temp.admin_dsn) as admin:
        admin.execute('ALTER TABLE message_opt_out NO FORCE ROW LEVEL SECURITY')
    assert s.ready() is False


def test_reused_event_id_for_a_different_address_is_a_conflict(database):
    from platform_communication.store import Conflict
    db,_=database;s=OutboxStore(db);w=uuid4()
    s.record_opt_out(w,'email','one@example.invalid','owner.global','evt-shared')
    with pytest.raises(Conflict):s.record_opt_out(w,'email','two@example.invalid','owner.global','evt-shared')
    with pytest.raises(Conflict):s.record_opt_out(w,'*','one@example.invalid','owner.global','evt-shared')
    assert s.record_opt_out(w,'email','one@example.invalid','owner.global','evt-shared')=='existing'


@pytest.mark.parametrize('subject',['   ','a\x7fb','a\u0085b','a b','a b'])
def test_subject_rejects_blank_and_unicode_control_or_separator(database,subject):
    db,_=database;s=OutboxStore(db)
    with pytest.raises(ValueError):s.create(uuid4(),'bad-subject','email','a@example.invalid','hi','plain',subject=subject)


def test_fingerprint_without_subject_keeps_the_pre_subject_form():
    import hashlib

    from platform_communication.store import fingerprint
    legacy=hashlib.sha256(json.dumps(['email','a@example.invalid','hi','plain',3],separators=(',',':')).encode()).hexdigest()
    assert fingerprint('email','a@example.invalid','hi','plain',3,None)==legacy
    assert fingerprint('email','a@example.invalid','hi','plain',3,'Quote')!=legacy
