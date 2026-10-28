"""Keyed recipient hashes and signed unsubscribe tokens from one service secret."""
import base64
import hashlib
import hmac
import os
import re
from uuid import UUID


def _b64(data):return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
def _unb64(text):return base64.urlsafe_b64decode(text+'='*(-len(text)%4))
class Keys:
    def __init__(self,secret):
        if not isinstance(secret,str) or len(secret)<32:raise ValueError('Invalid secret')
        root=secret.encode()
        # Separate derived keys, so a token never doubles as a recipient hash.
        self._hash=hmac.new(root,b'recipient-hash',hashlib.sha256).digest()
        self._token=hmac.new(root,b'unsubscribe-token',hashlib.sha256).digest()
    @classmethod
    def from_env(cls):return cls(os.environ.get('COMMUNICATION_SECRET'))
    def recipient_hash(self,channel,recipient):
        normalized=recipient.lower() if channel=='email' else recipient
        return hmac.new(self._hash,('recipient:'+normalized).encode(),hashlib.sha256).hexdigest()
    def unsubscribe_token(self,workspace,message_id):
        payload=workspace.bytes+message_id.bytes
        return _b64(payload)+'.'+_b64(hmac.new(self._token,payload,hashlib.sha256).digest()[:16])
    def read_unsubscribe_token(self,token):
        """(workspace, message id) for a token this key signed, else None."""
        # Only the exact string this class issues: no padding, extra characters or spare bits.
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}\.[A-Za-z0-9_-]{22}',token):return None
        body,mac=token.split('.')
        payload,given=_unb64(body),_unb64(mac)
        if _b64(payload)!=body or _b64(given)!=mac:return None
        if len(payload)!=32 or not hmac.compare_digest(given,hmac.new(self._token,payload,hashlib.sha256).digest()[:16]):return None
        return UUID(bytes=payload[:16]),UUID(bytes=payload[16:])
