import hashlib
import json
import re
import unicodedata
from uuid import UUID, uuid4

from psycopg.rows import dict_row

from .adapters import render_template
from .keys import Keys
from .migrations import MIGRATIONS


class Conflict(Exception):pass
class QueueFull(Exception):pass
PUBLIC='id,channel,recipient,subject,body,template,status,attempts,max_attempts,run_at,created_at'
PATTERNS={'email':r'[A-Za-z0-9.!#$%&*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}','sms':r'\+[1-9][0-9]{7,14}','push':r'[A-Za-z0-9_:.-]{10,512}','telegram':r'-?[0-9]{1,20}'}
OPT_OUT_SOURCES=['owner.global','email.list_unsubscribe','provider.blocked']
# Event ids the service writes itself; API callers cannot claim them ahead of time.
RESERVED_EVENT_PREFIXES=('unsubscribe:','provider:')
# Opt-outs hold only a keyed hash of the normalized address (see keys.Keys); each message stores
# the same hash, so SQL compares stored values and never needs the key.
OPTED_OUT="""EXISTS(SELECT 1 FROM message_opt_out o WHERE o.workspace_id=m.workspace_id AND o.channel IN (m.channel,'*')
    AND o.recipient_hash=m.recipient_hash)"""
def valid_recipient(channel,recipient):
    return channel in PATTERNS and isinstance(recipient,str) and len(recipient)<=512 and bool(re.fullmatch(PATTERNS[channel],recipient))
def valid_subject(subject):
    # No Unicode control, format or line/paragraph separator characters, and not blank.
    return isinstance(subject,str) and 1<=len(subject)<=200 and bool(subject.strip()) and not any(unicodedata.category(x)[0]=='C' or unicodedata.category(x) in ('Zl','Zp') for x in subject)
def fingerprint(channel,recipient,body,template,max_attempts,subject):
    # Without a subject the list keeps its pre-subject shape, so earlier keys still replay.
    parts=[channel,recipient,body,template,max_attempts]+([] if subject is None else [subject])
    return hashlib.sha256(json.dumps(parts,separators=(',',':')).encode()).hexdigest()
class OutboxStore:
    def __init__(self,database,*,keys=None,max_pending=10000):
        if type(max_pending) is not int or not 1<=max_pending<=10000:raise ValueError('Invalid capacity')
        self.db=database;self.max_pending=max_pending;self.keys=keys or Keys.from_env()
    def create(self,workspace,key,channel,recipient,body,template,max_attempts=3,subject=None):
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',key):raise ValueError('Invalid key')
        if not valid_recipient(channel,recipient):raise ValueError('Invalid recipient')
        if not isinstance(body,str) or not 1<=len(body)<=4096 or any(ord(x)<32 and x not in '\n\t' for x in body):raise ValueError('Invalid body')
        render_template(template,body)
        if template=='html' and channel!='email':raise ValueError('Invalid template')
        if type(max_attempts) is not int or not 1<=max_attempts<=10:raise ValueError('Invalid attempts')
        if subject is not None and (channel!='email' or not valid_subject(subject)):raise ValueError('Invalid subject')
        expected=fingerprint(channel,recipient,body,template,max_attempts,subject)
        with self.db.transaction(workspace) as conn, conn.cursor(row_factory=dict_row) as c:
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",('message-capacity:'+str(workspace),))
            c.execute('INSERT INTO message_outbox(workspace_id,id,event_key,fingerprint,channel,recipient,recipient_hash,subject,body,template,max_attempts) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(workspace_id,event_key) DO NOTHING',(workspace,uuid4(),key,expected,channel,recipient,self.keys.recipient_hash(channel,recipient),subject,body,template,max_attempts))
            c.execute(f"UPDATE message_outbox m SET status='suppressed' WHERE event_key=%s AND status='queued' AND {OPTED_OUT}",(key,))
            row=c.execute(f'SELECT {PUBLIC},fingerprint FROM message_outbox WHERE event_key=%s',(key,)).fetchone()
            if row.pop('fingerprint')!=expected:raise Conflict()
            if c.execute("SELECT count(*) FROM message_outbox WHERE status IN ('queued','leased','sending','uncertain')").fetchone()['count']>self.max_pending:raise QueueFull()
            return row
    def get(self,workspace,id):
        with self.db.transaction(workspace) as conn, conn.cursor(row_factory=dict_row) as c:
            return c.execute(f'SELECT {PUBLIC} FROM message_outbox WHERE id=%s',(id,)).fetchone()
    def list(self,workspace,limit=100,after=None):
        if not 1<=limit<=100:raise ValueError('Invalid limit')
        with self.db.transaction(workspace) as conn, conn.cursor(row_factory=dict_row) as c:
            return c.execute(f'SELECT {PUBLIC} FROM message_outbox WHERE (%s::uuid IS NULL OR id>%s::uuid) ORDER BY id LIMIT %s',(after,after,limit)).fetchall()
    def claim(self,workspace,lease_seconds=30):
        if type(lease_seconds) is not int or not 10<=lease_seconds<=300:raise ValueError('Invalid lease')
        with self.db.transaction(workspace) as conn, conn.cursor(row_factory=dict_row) as c:
            c.execute("UPDATE message_outbox SET status='uncertain',lease_token=NULL WHERE status='sending' AND lease_until<=clock_timestamp()")
            # Opt-out is checked before any attempt is counted; an expired presend lease gives its attempt back.
            c.execute(f"UPDATE message_outbox m SET status='suppressed',attempts=attempts-(status='leased')::int,lease_token=NULL,lease_until=NULL WHERE (status='queued' OR (status='leased' AND lease_until<=clock_timestamp())) AND {OPTED_OUT}")
            c.execute("UPDATE message_outbox SET status='dead',lease_token=NULL WHERE status='leased' AND lease_until<=clock_timestamp() AND attempts>=max_attempts")
            return c.execute("""WITH candidate AS (SELECT id FROM message_outbox WHERE attempts<max_attempts AND ((status='queued' AND run_at<=clock_timestamp()) OR (status='leased' AND lease_until<=clock_timestamp())) ORDER BY run_at,id FOR UPDATE SKIP LOCKED LIMIT 1) UPDATE message_outbox m SET status='leased',attempts=attempts+1,lease_token=%s,lease_until=clock_timestamp()+%s*interval '1 second' FROM candidate WHERE m.id=candidate.id RETURNING m.*""",(uuid4(),lease_seconds)).fetchone()
    def mark_sending(self,workspace,id,token):
        with self.db.transaction(workspace) as c:
            # An opt-out recorded after the claim still wins: suppress instead of sending.
            if c.execute(f"UPDATE message_outbox m SET status='suppressed',attempts=attempts-1,lease_token=NULL,lease_until=NULL WHERE id=%s AND lease_token=%s AND status='leased' AND {OPTED_OUT} RETURNING id",(id,token)).fetchone():return False
            return bool(c.execute("UPDATE message_outbox SET status='sending' WHERE id=%s AND lease_token=%s AND status='leased' AND lease_until>clock_timestamp() RETURNING id",(id,token)).fetchone())
    def unsubscribe_target(self,token):
        """(workspace, message) for a valid signed token of an email message, else None."""
        found=self.keys.read_unsubscribe_token(token)
        if found is None:return None
        row=self.get(found[0],found[1])
        return (found[0],row) if row is not None and row['channel']=='email' else None
    def unsubscribe(self,token):
        """Record an RFC 8058 one-click opt-out; False when the token names no email message."""
        target=self.unsubscribe_target(token)
        if target is None:return False
        workspace,row=target
        event='unsubscribe:'+str(row['id'])
        try:self.record_opt_out(workspace,'email',row['recipient'],'email.list_unsubscribe',event,internal=True)
        except Conflict:
            # The event id is already bound to another address; the click must still block this one.
            self.record_opt_out(workspace,'email',row['recipient'],'email.list_unsubscribe',event+':'+self.keys.recipient_hash('email',row['recipient'])[:16],internal=True)
        return True
    def record_opt_out(self,workspace,channel,recipient,source,event_id,*,internal=False):
        """``created`` or ``existing``; a replayed event id or an already blocked address changes nothing.

        Reusing an event id for a different channel or address raises Conflict instead of
        reporting ``existing`` for an address that was never blocked."""
        if channel!='*' and channel not in PATTERNS:raise ValueError('Invalid channel')
        channels=list(PATTERNS) if channel=='*' else [channel]
        if not any(valid_recipient(x,recipient) for x in channels):raise ValueError('Invalid recipient')
        if source not in OPT_OUT_SOURCES:raise ValueError('Invalid source')
        if not isinstance(event_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',event_id):raise ValueError('Invalid event')
        if not internal and event_id.startswith(RESERVED_EVENT_PREFIXES):raise ValueError('Invalid event')
        hashed=self.keys.recipient_hash(next(x for x in channels if valid_recipient(x,recipient)),recipient)
        with self.db.transaction(workspace) as c:
            created=c.execute('INSERT INTO message_opt_out(workspace_id,channel,recipient_hash,source,event_id) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING channel',(workspace,channel,hashed,source,event_id)).fetchone()
            if created:return 'created'
            same=c.execute('SELECT channel=%s AND recipient_hash=%s FROM message_opt_out WHERE event_id=%s',(channel,hashed,event_id)).fetchone()
            if same is not None and not same[0]:raise Conflict()
            return 'existing'
    def finish(self,workspace,id,token,outcome,provider_id=None):
        if outcome not in ['delivered','retry','dead','uncertain']:raise ValueError('Invalid outcome')
        if provider_id is not None and (not isinstance(provider_id,str) or len(provider_id)>256):provider_id=None
        with self.db.transaction(workspace) as c:
            return bool(c.execute("""UPDATE message_outbox SET status=CASE WHEN %s='retry' THEN CASE WHEN attempts>=max_attempts THEN 'dead' ELSE 'queued' END ELSE %s END,run_at=clock_timestamp()+least(3600,power(2,attempts)::int)*interval '1 second',provider_id=%s,lease_token=NULL,lease_until=NULL WHERE id=%s AND lease_token=%s AND status='sending' AND lease_until>clock_timestamp() RETURNING id""",(outcome,outcome,provider_id,id,token)).fetchone())
    def ready(self):
        with self.db.transaction(UUID(int=0)) as c:
            # Check every operation individually: a comma privilege list means ANY.
            required_permissions=c.execute("""SELECT has_schema_privilege(current_user,'public','USAGE')
                AND has_table_privilege(current_user,'public.platform_schema_migrations','SELECT')
                AND has_table_privilege(current_user,'public.message_outbox','SELECT')
                AND has_table_privilege(current_user,'public.message_outbox','INSERT')
                AND has_table_privilege(current_user,'public.message_outbox','UPDATE')
                AND has_table_privilege(current_user,'public.message_opt_out','SELECT')
                AND has_table_privilege(current_user,'public.message_opt_out','INSERT')""").fetchone()[0]
            if not required_permissions:return False
            history=c.execute('SELECT version,checksum FROM platform_schema_migrations WHERE namespace=%s ORDER BY version',('communication',)).fetchall()
            if history!=[(m.version,m.checksum) for m in MIGRATIONS]:return False
            row=c.execute("SELECT count(*)=2 AND bool_and(relrowsecurity AND relforcerowsecurity) FROM pg_class WHERE oid IN (to_regclass('message_outbox'),to_regclass('message_opt_out'))").fetchone()
            c.execute('SELECT status,lease_token,fingerprint,subject,recipient_hash FROM message_outbox LIMIT 0')
            c.execute('SELECT channel,recipient_hash FROM message_opt_out LIMIT 0')
            return bool(row and row[0])
