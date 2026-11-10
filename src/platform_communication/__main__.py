"""Explicit service lifecycle; migrations never run at API startup."""
import argparse
import os

from platform_backend_core import Database, MigrationRunner, TokenVerifier

from .app import create_app
from .migrations import MIGRATIONS


def _worker(*,until_empty):
    import signal
    from uuid import UUID

    from ._drain import drain, retention_days, scheduled_run
    from .adapters import configured_adapters
    from .store import OutboxStore
    from .worker import DeliveryWorker
    workspace=UUID(os.environ['COMMUNICATION_WORKSPACE_ID'])
    adapters=configured_adapters()
    if not any(a.configured for a in adapters.values()):raise ValueError('No delivery adapters')
    keep_days=retention_days(os.environ)  # a bad value fails before any message is sent
    database=Database(os.environ['DATABASE_URL'])
    store=OutboxStore(database)
    worker=DeliveryWorker(store,adapters)
    running=True
    def stop(*args):
        nonlocal running
        running=False
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        if until_empty:return scheduled_run(worker,store,workspace,keep_days=keep_days,running=lambda:running)
        return drain(worker,workspace,until_empty=False,running=lambda:running)
    finally:database.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['serve','migrate','worker'])
    p.add_argument('--until-empty',action='store_true',help='worker: drain due messages, then exit (for a scheduled job)')
    args=p.parse_args()
    try:
        if args.command=='migrate':
            MigrationRunner(os.environ['DATABASE_URL'],namespace='communication').apply(MIGRATIONS)
            return
        if args.command=='worker':
            from . import _heartbeat
            try:handled=_worker(until_empty=args.until_empty)
            except BaseException:
                if args.until_empty:_heartbeat.send(False,0)  # a failed cron run alerts now
                raise
            if args.until_empty:_heartbeat.send(True,handled)
            return
        verifier=TokenVerifier(issuer=os.environ['JWT_ISSUER'],audience=os.environ['JWT_AUDIENCE'],public_key=os.environ.get('JWT_PUBLIC_KEY'),jwks_url=os.environ.get('JWT_JWKS_URL'))
        app=create_app(Database(os.environ['DATABASE_URL']),verifier)
        import uvicorn
        uvicorn.run(app,host='0.0.0.0',port=int(os.environ.get('PORT','8080')),access_log=False,limit_concurrency=100)
    except Exception:  # noqa: BLE001 - startup errors are reported without configuration values
        raise SystemExit('Service configuration or dependency unavailable') from None
if __name__=='__main__':main()
