from __future__ import annotations

from email.message import Message
from typing import Optional

from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend


def _decode_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ''
    charset = part.get_content_charset() or 'utf-8'
    try:
        return payload.decode(charset, errors='replace')
    except LookupError:
        return payload.decode('utf-8', errors='replace')


def _extract_text_body(message: Message) -> Optional[str]:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == 'text/plain':
                return _decode_part(part)
        return None
    return _decode_part(message)


class DecodingConsoleEmailBackend(ConsoleEmailBackend):
    """
    Console backend that prints a decoded plain-text body to keep copy/paste URLs intact.
    """

    def write_message(self, message) -> None:
        email_message = message.message()
        body = _extract_text_body(email_message)
        if body is None:
            super().write_message(message)
            return

        subject = email_message.get('Subject', '')
        to = email_message.get('To', '')
        from_address = email_message.get('From', '')
        reply_to = email_message.get('Reply-To', '')

        if subject:
            self.stream.write(f'Subject: {subject}\n')
        if from_address:
            self.stream.write(f'From: {from_address}\n')
        if to:
            self.stream.write(f'To: {to}\n')
        if reply_to:
            self.stream.write(f'Reply-To: {reply_to}\n')
        self.stream.write('\n')
        self.stream.write(body)
        if not body.endswith('\n'):
            self.stream.write('\n')
