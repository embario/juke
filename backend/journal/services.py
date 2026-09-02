import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.utils import timezone

from journal.models import JournalAuthorizationCode


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode('ascii')).hexdigest()


def issue_authorization_code(*, user, client_id, redirect_uri, state, code_challenge):
    code = secrets.token_urlsafe(48)
    JournalAuthorizationCode.objects.create(
        user=user,
        code_digest=sha256_hex(code),
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
        code_challenge=code_challenge,
        expires_at=timezone.now() + timedelta(seconds=settings.JOURNAL_AUTH_CODE_TTL_SECONDS),
    )
    separator = '&' if '?' in redirect_uri else '?'
    return code, f'{redirect_uri}{separator}{urlencode({"code": code, "state": state})}'


class JournalChatUnavailable(Exception):
    pass


def generate_chat_response(*, message: str, current_track: str | None) -> str:
    api_key = getattr(settings, 'OPENAI_API_KEY', '')
    if not api_key:
        raise JournalChatUnavailable('Journal chat is temporarily unavailable.')

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    track_context = current_track or 'No current track is available.'
    response = client.chat.completions.create(
        model=settings.JOURNAL_CHAT_MODEL,
        messages=[
            {
                'role': 'system',
                'content': (
                    'You are Juke Journal, a thoughtful and concise music companion. '
                    'Respond to the listener without claiming facts you cannot verify. '
                    'Do not ask for sensitive personal information. The supplied message '
                    'was explicitly submitted for this reply and must not be retained.'
                ),
            },
            {'role': 'system', 'content': f'Current track metadata: {track_context}'},
            {'role': 'user', 'content': message},
        ],
        max_tokens=350,
        temperature=0.7,
    )
    content = response.choices[0].message.content
    if not content:
        raise JournalChatUnavailable('Journal chat returned no response.')
    return content.strip()
