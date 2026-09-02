from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions
from rest_framework.authentication import SessionAuthentication, TokenAuthentication, get_authorization_header


class JournalTokenAuthentication(TokenAuthentication):
    """Accept Juke's historical `Token` header and Journal's `Bearer` header."""

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() not in {b'token', b'bearer'}:
            return None
        if len(auth) == 1:
            raise exceptions.AuthenticationFailed(_('Invalid token header. No credentials provided.'))
        if len(auth) > 2:
            raise exceptions.AuthenticationFailed(_('Invalid token header. Token string should not contain spaces.'))
        try:
            token = auth[1].decode()
        except UnicodeError as exc:
            raise exceptions.AuthenticationFailed(_('Invalid token header.')) from exc
        return self.authenticate_credentials(token)


JOURNAL_AUTHENTICATION_CLASSES = (JournalTokenAuthentication, SessionAuthentication)
