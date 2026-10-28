"""Only domain validation maps to 422; any other ValueError is a server bug (redacted 500).

Offline: the store is replaced or fails before touching the database.
"""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_http import auth

from platform_communication.adapters import render_template
from platform_communication.app import create_app
from platform_communication.keys import Keys
from platform_communication.store import InvalidInput, OutboxStore


class _NoDatabase:
    def ready(self):
        return False

    def close(self):
        pass

    def transaction(self, workspace):
        raise AssertionError('database must not be reached')


class _Adapter:
    configured = True


@pytest.fixture
def client():
    verifier, headers = auth()
    with TestClient(create_app(_NoDatabase(), verifier, adapters={'email': _Adapter()})) as c:
        yield c, headers('messages:read messages:write opt-outs:write', uuid4())


def test_invalid_input_is_a_value_error():
    assert issubclass(InvalidInput, ValueError)


def _store():
    return OutboxStore(_NoDatabase())


@pytest.mark.parametrize('call', [
    lambda: _store().create(uuid4(), 'bad key!', 'email', 'a@example.invalid', 'hi', 'plain'),
    lambda: _store().create(uuid4(), 'k', 'email', 'https://evil', 'hi', 'plain'),
    lambda: _store().create(uuid4(), 'k', 'email', 'a@example.invalid', 'a\x00b', 'plain'),
    lambda: _store().create(uuid4(), 'k', 'email', 'a@example.invalid', 'hi', '../../file'),
    lambda: _store().create(uuid4(), 'k', 'sms', '+12025550123', 'hi', 'html'),
    lambda: _store().create(uuid4(), 'k', 'email', 'a@example.invalid', 'hi', 'plain', 11),
    lambda: _store().create(uuid4(), 'k', 'sms', '+12025550123', 'hi', 'plain', subject='x'),
    lambda: _store().list(uuid4(), 0),
    lambda: _store().record_opt_out(uuid4(), 'fax', 'a@example.invalid', 'owner.global', 'e'),
    lambda: _store().record_opt_out(uuid4(), 'email', 'not-an-email', 'owner.global', 'e'),
    lambda: _store().record_opt_out(uuid4(), 'email', 'a@example.invalid', 'made.up', 'e'),
    lambda: _store().record_opt_out(uuid4(), 'email', 'a@example.invalid', 'owner.global', 'unsubscribe:x'),
    lambda: render_template('../../file', 'hi'),
])
def test_store_validation_raises_invalid_input(call):
    with pytest.raises(InvalidInput):
        call()


@pytest.mark.parametrize('call', [
    lambda: Keys('short-secret'),
    lambda: OutboxStore(_NoDatabase(), max_pending=0),
    lambda: _store().claim(uuid4(), 1),
    lambda: _store().finish(uuid4(), uuid4(), uuid4(), 'made-up'),
])
def test_configuration_and_internal_errors_stay_plain_value_errors(call):
    # Startup secrets, capacity and worker-only arguments are not client input: never 422.
    with pytest.raises(ValueError) as caught:
        call()
    assert not isinstance(caught.value, InvalidInput)


def test_domain_validation_returns_422(client):
    c, h = client
    message = {'channel': 'email', 'recipient': 'https://evil', 'body': 'hi'}
    response = c.post('/v1/messages', headers=h, json=message)
    assert response.status_code == 422
    assert response.json() == {'detail': 'Invalid message'}
    message = {'channel': 'email', 'recipient': 'a@example.invalid', 'body': 'hi', 'template': 'nope'}
    assert c.post('/v1/messages', headers=h, json=message).status_code == 422
    opt_out = {'channel': 'email', 'recipient': 'a@example.invalid', 'source': 'made.up', 'event_id': 'e'}
    assert c.post('/v1/opt-outs', headers=h, json=opt_out).status_code == 422
    opt_out = {'channel': 'email', 'recipient': 'a@example.invalid', 'source': 'owner.global', 'event_id': 'provider:x'}
    assert c.post('/v1/opt-outs', headers=h, json=opt_out).status_code == 422


def test_unexpected_value_error_is_redacted_500(client, monkeypatch):
    def broken(self, workspace, limit=100, after=None):
        raise ValueError('secret-bearing internal detail')

    monkeypatch.setattr(OutboxStore, 'list', broken)
    c, h = client
    response = c.get('/v1/messages', headers=h)
    assert response.status_code == 500
    assert 'secret-bearing' not in response.text
    assert response.json() == {'detail': 'internal server error'}
