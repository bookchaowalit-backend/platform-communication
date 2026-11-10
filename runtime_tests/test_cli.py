"""The cron worker entry point fails closed: a run that cannot start exits with a generic message."""
import sys

import pytest

from platform_communication import __main__ as cli


@pytest.mark.parametrize('env',[{},{'COMMUNICATION_WORKSPACE_ID':'00000000-0000-0000-0000-000000000001','COMMUNICATION_RETENTION_DAYS':'3'}])
def test_cron_worker_without_config_reports_failure(monkeypatch,env):
    for name in ('COMMUNICATION_WORKSPACE_ID','COMMUNICATION_RETENTION_DAYS','HEARTBEAT_URL','HEARTBEAT_TOKEN'):
        monkeypatch.delenv(name,raising=False)
    for name,value in env.items():monkeypatch.setenv(name,value)
    beats=[]
    monkeypatch.setattr('platform_communication._heartbeat.send',lambda ok,handled:beats.append((ok,handled)))
    monkeypatch.setattr('platform_communication.adapters.configured_adapters',lambda:{'email':type('A',(),{'configured':True})()})
    monkeypatch.setattr(cli,'Database',lambda dsn:pytest.fail('no database before config is valid'))
    monkeypatch.setattr(sys,'argv',['platform_communication','worker','--until-empty'])
    with pytest.raises(SystemExit) as stopped:cli.main()
    assert str(stopped.value)=='Service configuration or dependency unavailable'
    assert beats==[(False,0)]
