"""Keyed recipient hashes and RFC 8058 one-click unsubscribe."""
import hashlib
import json
import os
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from platform_backend_core import Database, MigrationRunner
from platform_backend_core.testing import temporary_database
from test_http import auth

from platform_communication.adapters import ResendAdapter, configured_adapters
from platform_communication.app import create_app
from platform_communication.keys import Keys
from platform_communication.migrations import MIGRATIONS
from platform_communication.store import OutboxStore
from platform_communication.worker import DeliveryWorker

SECRET='a'*20+'b'*20


@pytest.fixture
def database():
    dsn=os.environ.get('PLATFORM_TEST_DSN')
    if not dsn:pytest.skip('explicit disposable PostgreSQL DSN required')
    with temporary_database(dsn,prefix='unsub_') as temp:
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


@pytest.mark.parametrize('secret',[None,'','short-secret'])
def test_keys_require_a_long_secret(secret):
    with pytest.raises(ValueError):Keys(secret)


def test_store_fails_closed_without_a_secret(monkeypatch):
    monkeypatch.delenv('COMMUNICATION_SECRET')
    with pytest.raises(ValueError):OutboxStore(object())


def test_recipient_hash_is_keyed_and_normalizes_email():
    a,b=Keys(SECRET),Keys(SECRET[::-1])
    assert a.recipient_hash('email','Person@Example.invalid')==a.recipient_hash('email','person@example.invalid')
    assert a.recipient_hash('email','person@example.invalid')!=b.recipient_hash('email','person@example.invalid')
    assert a.recipient_hash('email','person@example.invalid')!=hashlib.sha256(b'recipient:person@example.invalid').hexdigest()


def test_stored_hashes_use_the_key_and_still_suppress(database):
    db,temp=database;s=OutboxStore(db,keys=Keys(SECRET));w=uuid4();adapter=Recording()
    s.record_opt_out(w,'email','person@example.invalid','owner.global','evt-1')
    row=s.create(w,'blocked','email','Person@Example.invalid','hi','plain')
    assert row['status']=='suppressed'
    expected=Keys(SECRET).recipient_hash('email','person@example.invalid')
    with psycopg.connect(temp.admin_dsn) as admin:
        assert admin.execute('SELECT recipient_hash FROM message_opt_out').fetchone()[0]==expected
        assert admin.execute('SELECT recipient_hash FROM message_outbox').fetchone()[0]==expected
    other=OutboxStore(db,keys=Keys(SECRET[::-1]))
    assert other.create(w,'other-key','email','person@example.invalid','hi','plain')['status']=='queued'
    DeliveryWorker(s,{'email':adapter}).run_one(w)


def test_unsubscribe_token_roundtrip_and_rejection():
    k=Keys(SECRET);w,m=uuid4(),uuid4()
    token=k.unsubscribe_token(w,m)
    assert k.read_unsubscribe_token(token)==(w,m)
    assert Keys(SECRET[::-1]).read_unsubscribe_token(token) is None
    tampered=token[:-2]+('AA' if token[-2:]!='AA' else 'BB')
    for bad in [tampered,'',token+'x','not.a.token','a'*500,None]:
        assert k.read_unsubscribe_token(bad) is None


def test_resend_sends_one_click_unsubscribe_headers():
    requests=[]
    def fixture(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'id':'fixture'})
    m={'id':UUID(int=1),'workspace_id':UUID(int=2),'recipient':'a@example.invalid','body':'hi','template':'plain','subject':None}
    a=ResendAdapter('synthetic','from@example.invalid',unsubscribe_url=lambda x:'https://mail.example.invalid/v1/unsubscribe?t=T'+str(x['id'].int),transport=httpx.MockTransport(fixture))
    a.send(m)
    assert requests[0]['headers']=={'List-Unsubscribe':'<https://mail.example.invalid/v1/unsubscribe?t=T1>','List-Unsubscribe-Post':'List-Unsubscribe=One-Click'}
    ResendAdapter('synthetic','from@example.invalid',transport=httpx.MockTransport(fixture)).send(m)
    assert 'headers' not in requests[1]


@pytest.mark.parametrize('url,linked',[('https://mail.example.invalid',True),('http://mail.example.invalid',False),('https://mail.example.invalid/path?q=1',False),(None,False)])
def test_configured_adapters_only_link_a_plain_https_origin(monkeypatch,url,linked):
    monkeypatch.setenv('RESEND_API_KEY','synthetic');monkeypatch.setenv('RESEND_FROM','from@example.invalid')
    if url:monkeypatch.setenv('COMMUNICATION_PUBLIC_URL',url)
    else:monkeypatch.delenv('COMMUNICATION_PUBLIC_URL',raising=False)
    email=configured_adapters()['email']
    assert (email.unsubscribe_url is not None)==linked
    if linked:
        link=email.unsubscribe_url({'id':UUID(int=1),'workspace_id':UUID(int=2)})
        assert link.startswith('https://mail.example.invalid/v1/unsubscribe?t=')
        assert Keys(SECRET).read_unsubscribe_token(link.split('t=',1)[1])==(UUID(int=2),UUID(int=1))


def test_one_click_post_records_opt_out_and_later_mail_is_suppressed(database):
    db,_=database;verifier,headers=auth();w=uuid4();k=Keys(SECRET)
    with TestClient(create_app(db,verifier,adapters={'email':Recording()})) as c:
        h=headers('messages:write messages:read',w)
        first=c.post('/v1/messages',headers=h,json={'channel':'email','recipient':'person@example.invalid','body':'hi'}).json()
        url='/v1/unsubscribe?t='+k.unsubscribe_token(w,UUID(first['id']))
        form={'Content-Type':'application/x-www-form-urlencoded'}
        assert c.post(url,headers=form,content='List-Unsubscribe=One-Click').status_code==200
        assert c.post(url,headers=form,content='List-Unsubscribe=One-Click').status_code==200
        h['Idempotency-Key']='second'
        again=c.post('/v1/messages',headers=h,json={'channel':'email','recipient':'person@example.invalid','body':'hi'})
        assert again.json()['status']=='suppressed'


def test_unsubscribe_rejects_bad_tokens_and_bodies_without_leaking(database):
    db,_=database;verifier,headers=auth();w=uuid4();k=Keys(SECRET)
    with TestClient(create_app(db,verifier,adapters={'email':Recording()})) as c:
        h=headers('messages:write',w)
        row=c.post('/v1/messages',headers=h,json={'channel':'email','recipient':'person@example.invalid','body':'hi'}).json()
        form={'Content-Type':'application/x-www-form-urlencoded'}
        good='/v1/unsubscribe?t='+k.unsubscribe_token(w,UUID(row['id']))
        for url in ['/v1/unsubscribe?t='+k.unsubscribe_token(uuid4(),UUID(row['id'])),'/v1/unsubscribe?t=bogus','/v1/unsubscribe']:
            r=c.post(url,headers=form,content='List-Unsubscribe=One-Click')
            assert r.status_code==404 and 'person' not in r.text
        r=c.post(good,headers=form,content='something-else')
        assert r.status_code==400
        page=c.get(good)
        assert page.status_code==200 and 'person@example.invalid' not in page.text and '<form method="post"' in page.text
        assert page.headers['content-type'].startswith('text/html')
        assert page.headers.get('cache-control')=='no-store'


@pytest.mark.parametrize('event_id',['unsubscribe:00000000-0000-0000-0000-000000000001','provider:00000000-0000-0000-0000-000000000001'])
def test_api_cannot_claim_reserved_event_ids(database,event_id):
    db,_=database;verifier,headers=auth();w=uuid4()
    with TestClient(create_app(db,verifier,adapters={'email':Recording()})) as c:
        r=c.post('/v1/opt-outs',headers=headers('opt-outs:write',w),json={'channel':'email','recipient':'other@example.invalid','source':'owner.global','event_id':event_id})
        assert r.status_code==422


def test_unsubscribe_wins_even_if_its_event_id_was_used(database):
    db,_=database;s=OutboxStore(db,keys=Keys(SECRET));w=uuid4()
    row=s.create(w,'victim','email','person@example.invalid','hi','plain')
    s.record_opt_out(w,'email','other@example.invalid','email.list_unsubscribe','unsubscribe:'+str(row['id']),internal=True)
    assert s.unsubscribe(Keys(SECRET).unsubscribe_token(w,row['id'])) is True
    assert s.create(w,'after','email','person@example.invalid','hi','plain')['status']=='suppressed'


def test_only_the_canonical_token_string_verifies():
    k=Keys(SECRET);w,m=uuid4(),uuid4();token=k.unsubscribe_token(w,m)
    body,tag=token.split('.')
    variants=[token+'***','***'+token,token+'==',token+'\n',body+'.'+tag[:-1]+('B' if tag[-1]=='A' else 'A')]
    assert [k.read_unsubscribe_token(v) for v in variants]==[None]*len(variants)


def test_outbox_rows_cannot_lack_a_recipient_hash(database):
    _,temp=database
    with psycopg.connect(temp.admin_dsn) as admin, pytest.raises(psycopg.errors.NotNullViolation):
        admin.execute("SELECT set_config('app.workspace_id',%s,false)",(str(uuid4()),))
        admin.execute("INSERT INTO message_outbox(workspace_id,id,event_key,fingerprint,channel,recipient,body,template,max_attempts) VALUES (current_setting('app.workspace_id')::uuid,%s,'k','f','email','a@example.invalid','hi','plain',1)",(uuid4(),))
