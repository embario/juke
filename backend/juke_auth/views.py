import logging

from django.conf import settings
from django.contrib.auth import login, logout
from django.http import HttpResponseRedirect, JsonResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.module_loading import import_string

from rest_framework import viewsets, permissions, status, generics
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_registration.api.views.register import RegisterView
try:
    from rest_registration.api.views import VerifyRegistrationView
except ImportError:  # pragma: no cover - fallback for older rest_registration layouts
    from rest_registration.api.views.register import VerifyRegistrationView

from social_django.utils import load_backend, load_strategy
from social_core.exceptions import AuthConnectionError
from social_django import views as social_views

from juke_auth.serializers import (
    JukeUserSerializer,
    MusicProfileSerializer,
    MusicProfileSearchSerializer,
    GlobePointSerializer,
)
from juke_auth.models import JukeUser, MusicProfile


logger = logging.getLogger(__name__)

SOCIAL_AUTH_PROVIDER = 'spotify'


def _social_auth_error_response(request, error_code: str, detail: str, status_code: int):
    accept = request.META.get('HTTP_ACCEPT', '')
    if 'application/json' in accept:
        return JsonResponse({'detail': detail, 'error': error_code}, status=status_code)
    error_url = f"{settings.FRONTEND_URL.rstrip('/')}/login?error={error_code}"
    return HttpResponseRedirect(error_url)


def spotify_complete(request, *args, **kwargs):
    try:
        return social_views.complete(request, backend=SOCIAL_AUTH_PROVIDER, *args, **kwargs)
    except AuthConnectionError as exc:
        logger.warning('Spotify auth connection error', exc_info=exc)
        return _social_auth_error_response(
            request,
            error_code='spotify_unavailable',
            detail='Spotify authentication is temporarily unavailable. Please try again.',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except Exception as exc:
        logger.exception('Spotify auth failed', exc_info=exc)
        return _social_auth_error_response(
            request,
            error_code='spotify_auth_failed',
            detail='Spotify authentication failed. Please try again.',
            status_code=status.HTTP_400_BAD_REQUEST,
        )


def _send_register_verification_email(user, request=None):
    sender_path = settings.REST_REGISTRATION.get(
        'REGISTER_VERIFICATION_EMAIL_SENDER',
        'rest_registration.verification_notifications.send_register_verification_email_notification',
    )
    sender = import_string(sender_path)
    attempts = [
        {'user': user, 'request': request, 'user_address': user.email},
        {'user': user, 'request': request},
        {'user': user, 'user_address': user.email},
        {'user': user, 'email': user.email},
        {'user': user},
    ]
    for kwargs in attempts:
        try:
            sender(**kwargs)
            return
        except TypeError:
            continue
    sender(user)


def _login_user(request, user):
    auth_backends = getattr(settings, 'AUTHENTICATION_BACKENDS', []) or []
    backend = auth_backends[0] if auth_backends else 'django.contrib.auth.backends.ModelBackend'
    login(request, user, backend=backend)


class JukeUserViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows Juke users to be viewed or edited.
    """
    queryset = JukeUser.objects.all().order_by('-date_joined')
    serializer_class = JukeUserSerializer
    permission_classes = [permissions.IsAuthenticated]


class IsProfileOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user_id == request.user.id


class MusicProfileViewSet(viewsets.ModelViewSet):
    queryset = MusicProfile.objects.select_related('user')
    serializer_class = MusicProfileSerializer
    permission_classes = [permissions.IsAuthenticated, IsProfileOwnerOrReadOnly]
    lookup_field = 'username'
    lookup_url_kwarg = 'username'
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_queryset(self):
        return self.queryset

    def list(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Music profiles cannot be listed. Use the search endpoint instead.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def get_object(self):
        username = self.kwargs.get(self.lookup_url_kwarg or self.lookup_field)
        queryset = self.filter_queryset(self.get_queryset())
        obj = get_object_or_404(queryset, user__username=username)
        self.check_object_permissions(self.request, obj)
        return obj

    def perform_create(self, serializer):
        request_user = self.request.user
        if MusicProfile.objects.filter(user=request_user).exists():
            raise ValidationError({'detail': 'Profile already exists for this user.'})
        serializer.save(user=request_user)

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='me')
    def me(self, request):
        profile, _ = MusicProfile.objects.get_or_create(user=request.user)
        if request.method in ['PUT', 'PATCH']:
            serializer = self.get_serializer(profile, data=request.data, partial=request.method == 'PATCH')
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        serializer = self.get_serializer(profile)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='search')
    def search(self, request):
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response({'results': []})
        queryset = self.get_queryset().filter(
            Q(user__username__icontains=query) | Q(display_name__icontains=query)
        )[:10]
        serializer = MusicProfileSearchSerializer(queryset, many=True)
        return Response({'results': serializer.data})

    @action(detail=False, methods=['get'], url_path='globe')
    def globe(self, request):
        """Bulk geo-point retrieval with LOD filtering for the Juke World globe."""
        try:
            min_lat = float(request.query_params.get('min_lat', -90))
            max_lat = float(request.query_params.get('max_lat', 90))
            min_lng = float(request.query_params.get('min_lng', -180))
            max_lng = float(request.query_params.get('max_lng', 180))
            zoom = int(request.query_params.get('zoom', 1))
            limit = min(int(request.query_params.get('limit', 5000)), 10000)
        except (ValueError, TypeError):
            return Response(
                {'detail': 'Invalid query parameters.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # LOD clout threshold based on zoom level
        if zoom <= 4:
            clout_threshold = 0.5
        elif zoom <= 8:
            clout_threshold = 0.2
        elif zoom <= 12:
            clout_threshold = 0.05
        else:
            clout_threshold = 0.0

        queryset = MusicProfile.objects.select_related('user').filter(
            city_lat__isnull=False,
            city_lng__isnull=False,
            city_lat__gte=min_lat,
            city_lat__lte=max_lat,
            city_lng__gte=min_lng,
            city_lng__lte=max_lng,
            clout__gte=clout_threshold,
        ).order_by('-clout')[:limit]

        serializer = GlobePointSerializer(queryset, many=True)
        return Response(serializer.data)


class TokenLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = AuthTokenSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)
        _login_user(request, user)
        return Response({'token': token.key}, status=status.HTTP_200_OK)


class TokenLogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if request.auth:
            # Keep token valid for future logins, only clear session.
            logout(request)
        else:
            logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SocialAuth(generics.CreateAPIView):

    def create(self, request, *args, **kwargs):
        redirect = request.path

        try:
            access_token = request.data['access_token']
        except KeyError:
            return Response({'detail': "'access_token' is required."}, status=status.HTTP_400_BAD_REQUEST)

        strategy = load_strategy(request)
        backend = load_backend(strategy, SOCIAL_AUTH_PROVIDER, redirect)
        request.social_auth_backend = backend

        try:
            user = backend.do_auth(access_token, expires=None, *args, **kwargs)
            user_serializer = JukeUserSerializer(user, context={'request': request})
            return Response(user_serializer.data, status=status.HTTP_200_OK)
        except AuthConnectionError as exc:
            logger.warning('Spotify auth connection error', exc_info=exc)
            return Response(
                {'detail': 'Spotify authentication is temporarily unavailable. Please try again.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as e:
            return Response({'detail': e.args[0]}, status=status.HTTP_400_BAD_REQUEST)


class JukeRegisterView(RegisterView):
    def post(self, request, *args, **kwargs):
        if getattr(settings, 'DISABLE_REGISTRATION', False):
            return Response(
                {'detail': 'Registration is temporarily disabled. Please try again later.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().post(request, *args, **kwargs)


class ResendRegistrationVerificationView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        if getattr(settings, 'DISABLE_REGISTRATION', False):
            return Response(
                {'detail': 'Registration is temporarily disabled. Please try again later.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        email = (request.data.get('email') or '').strip()
        username = (request.data.get('username') or '').strip()
        if not email and not username:
            return Response(
                {'detail': 'Email or username is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = None
        if email:
            user = JukeUser.objects.filter(email__iexact=email).first()
        if not user and username:
            user = JukeUser.objects.filter(username__iexact=username).first()

        if not user:
            return Response(
                {'detail': 'No account found for that email or username.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.is_active:
            return Response(
                {'detail': 'Account is already verified. Please sign in.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _send_register_verification_email(user, request=request)

        return Response(
            {'detail': 'Verification email sent. Please check your inbox.'},
            status=status.HTTP_200_OK,
        )


class JukeVerifyRegistrationView(VerifyRegistrationView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code != status.HTTP_200_OK:
            return response

        user_id = request.data.get('user_id')
        if not user_id:
            return response

        user = JukeUser.objects.filter(pk=user_id).first()
        if not user:
            return response

        token, _ = Token.objects.get_or_create(user=user)
        _login_user(request, user)
        return Response(
            {'detail': 'Account verified.', 'token': token.key, 'username': user.username},
            status=status.HTTP_200_OK,
        )
