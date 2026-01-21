import logging

from django.contrib.auth import login, logout

from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, permissions, status, generics
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated

from social_django.utils import load_backend, load_strategy

from juke_auth.serializers import (
    JukeUserSerializer,
    MusicProfileSerializer,
    MusicProfileSearchSerializer,
)
from juke_auth.models import JukeUser, MusicProfile


logger = logging.Logger(__name__)

SOCIAL_AUTH_PROVIDER = 'spotify'


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


class TokenLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = AuthTokenSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)
        login(request, user)
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
        except Exception as e:
            return Response({'detail': e.args[0]}, status=status.HTTP_400_BAD_REQUEST)
