from uuid import UUID

from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from platform_backend_core import create_app as base_app
from platform_backend_core import require_scope
from pydantic import BaseModel, ConfigDict, Field

from .adapters import configured_adapters
from .store import Conflict, InvalidInput, OutboxStore, QueueFull


class Message(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    channel:str=Field(max_length=16)
    recipient:str=Field(min_length=1,max_length=512)
    body:str=Field(min_length=1,max_length=4096)
    subject:str|None=Field(default=None,min_length=1,max_length=200)
    template:str=Field(default='plain',max_length=16)
    max_attempts:int=Field(default=3,ge=1,le=10)
class OptOut(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    channel:str=Field(max_length=16)
    recipient:str=Field(min_length=1,max_length=512)
    source:str=Field(max_length=32)
    event_id:str=Field(min_length=1,max_length=128)
def create_app(database,verifier,*,adapters=None):
    app=base_app('communication',database,verifier,max_body_bytes=32768);store=OutboxStore(database)
    adapters=configured_adapters() if adapters is None else dict(adapters)
    app.state.adapters=adapters
    app.state.readiness_checks['outbox_schema']=store.ready
    app.state.readiness_checks['delivery_adapters']=lambda: any(x.configured for x in adapters.values())
    @app.exception_handler(QueueFull)
    async def full(request,exc):return JSONResponse({'detail':'Outbox capacity reached'},429)
    # Only the domain InvalidInput is a client error; any other exception (an unexpected
    # ValueError included) is a server bug and becomes the shared core's redacted 500.
    @app.exception_handler(InvalidInput)
    async def invalid(request,exc):return JSONResponse({'detail':'Invalid message'},422)
    @app.exception_handler(Conflict)
    async def conflict(request,exc):return JSONResponse({'detail':'Idempotency conflict'},409)
    @app.post('/v1/messages',status_code=202)
    def create(body:Message,key:str=Header(alias='Idempotency-Key',max_length=128),p=Depends(require_scope('messages:write'))):
        adapter=adapters.get(body.channel)
        if adapter is None or not adapter.configured:raise HTTPException(503,'Delivery unavailable')
        return store.create(p.workspace,key,body.channel,body.recipient,body.body,body.template,body.max_attempts,body.subject)
    @app.post('/v1/opt-outs')
    def opt_out(body:OptOut,p=Depends(require_scope('opt-outs:write'))):
        outcome=store.record_opt_out(p.workspace,body.channel,body.recipient,body.source,body.event_id)
        return JSONResponse({'outcome':outcome},201 if outcome=='created' else 200)
    @app.get('/v1/messages')
    def listing(limit:int=Query(100,ge=1,le=100),after:UUID|None=None,p=Depends(require_scope('messages:read'))):return store.list(p.workspace,limit,after)
    @app.get('/v1/messages/{id}')
    def get(id:UUID,p=Depends(require_scope('messages:read'))):
        row=store.get(p.workspace,id)
        if row is None:raise HTTPException(404,'Not found')
        return row
    page_headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'; form-action 'self'; frame-ancestors 'none'"}
    def page(text,status=200):
        return HTMLResponse('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Unsubscribe</title>'+text,status,headers=page_headers)
    # Unauthenticated by design: the signed token is the authority, and pages never show the address.
    @app.get('/v1/unsubscribe')
    def unsubscribe_page(t:str|None=Query(None,max_length=100)):
        if store.unsubscribe_target(t) is None:return page('<p>This link is not valid.</p>',404)
        return page('<p>Stop receiving these emails?</p><form method="post"><input type="hidden" name="List-Unsubscribe" value="One-Click"><button type="submit">Unsubscribe</button></form>')
    @app.post('/v1/unsubscribe')
    async def unsubscribe(request:Request,t:str|None=Query(None,max_length=100)):
        if (await request.body()).strip()!=b'List-Unsubscribe=One-Click':return page('<p>Invalid request.</p>',400)
        if not store.unsubscribe(t):return page('<p>This link is not valid.</p>',404)
        return page('<p>You are unsubscribed.</p>')
    return app
