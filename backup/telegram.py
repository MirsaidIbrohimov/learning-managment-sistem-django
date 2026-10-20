"""Bounded-memory multipart uploads; never expose HTTP exceptions or API bodies."""
import http.client
import json
import uuid

UPLOAD_LIMIT = 49_000_000  # Decimal MB, leaving room below Telegram's 50 MB limit.


class BackupError(Exception):
    pass


class Telegram:
    def __init__(self, token, chat, timeout=120):
        self.token, self.chat, self.timeout = token, chat, timeout

    def request(self, method, fields, path=None):
        if not self.token or not self.chat:
            raise BackupError('Telegram token/chat ID sozlanmagan.')
        boundary = uuid.uuid4().hex
        fields = {'chat_id': self.chat, **fields}
        prefix = b''
        for key, value in fields.items():
            prefix += (f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"'
                       f'\r\n\r\n{value}\r\n').encode()
        size = 0
        if path:
            size = path.stat().st_size
            if size > UPLOAD_LIMIT:
                raise BackupError('Telegram fayli 49 MB dan katta.')
            prefix += (f'--{boundary}\r\nContent-Disposition: form-data; name="document"; '
                       f'filename="{path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
        suffix = (('\r\n' if path else '') + f'--{boundary}--\r\n').encode()
        conn = http.client.HTTPSConnection('api.telegram.org', timeout=self.timeout)
        try:
            conn.putrequest('POST', f'/bot{self.token}/{method}')
            conn.putheader('Content-Type', f'multipart/form-data; boundary={boundary}')
            conn.putheader('Content-Length', str(len(prefix) + size + len(suffix)))
            conn.endheaders()
            conn.send(prefix)
            if path:
                with path.open('rb') as stream:
                    while chunk := stream.read(64 * 1024):
                        conn.send(chunk)
            conn.send(suffix)
            response = conn.getresponse()
            body = response.read(1024 * 1024 + 1)
            if response.status != 200:
                raise BackupError(f'Telegram HTTP xatosi: {response.status}.')
            if len(body) > 1024 * 1024 or json.loads(body).get('ok') is not True:
                raise BackupError('Telegram API ok=false yoki yaroqsiz javob.')
        except BackupError:
            raise
        except Exception:
            raise BackupError('Telegram transport/timeout/JSON xatosi.') from None
        finally:
            conn.close()

    def message(self, text):
        self.request('sendMessage', {'text': text})

    def document(self, path, caption):
        self.request('sendDocument', {'caption': caption}, path)
