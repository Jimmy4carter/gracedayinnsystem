from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.exceptions import ValidationError as ApiValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import UserProfile, GuestProfile
from .serializers import (UserProfileSerializer, UserCreateSerializer,
                          LoginSerializer, GuestProfileSerializer)
from .permissions import RoleActionPermission
from .api_audit import ApiAuditMixin
from .security import clear_account_login_failures, record_authentication_event
from .guests import duplicate_guest_groups, merge_guest_accounts


class UserProfileViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = UserProfile.objects.order_by('id')
    permission_classes = [RoleActionPermission]
    action_roles = {
        'login': set(),
        'register': set(),
        'list': {'admin', 'manager'},
        'retrieve': {'admin', 'manager'},
        'create': {'admin'},
        'update': {'admin'},
        'partial_update': {'admin'},
        'destroy': set(),
        'logout': {'admin', 'manager', 'receptionist', 'housekeeping', 'guest'},
        'me': {'admin', 'manager', 'receptionist', 'housekeeping', 'guest'},
        'update_me': {'admin', 'manager', 'receptionist', 'housekeeping', 'guest'},
        'duplicates': {'admin', 'manager', 'receptionist'},
        'merge_guest': {'admin', 'manager'},
    }
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['role', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']

    def get_serializer_class(self):
        if self.action in ('create',):
            return UserCreateSerializer
        return UserProfileSerializer

    def get_permissions(self):
        if self.action in ('login', 'register'):
            return [permissions.AllowAny()]
        return super().get_permissions()

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def login(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        clear_account_login_failures(user.username)
        record_authentication_event(request, 'api_login_success', user=user)
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserProfileSerializer(user).data,
        })

    @action(detail=False, methods=['post'])
    def logout(self, request):
        raw_token = request.data.get('refresh')
        if not raw_token:
            raise ApiValidationError({'refresh': 'A refresh token is required.'})
        try:
            token = RefreshToken(raw_token)
            token.blacklist()
        except TokenError as exc:
            raise ApiValidationError({'refresh': 'The refresh token is invalid or expired.'}) from exc
        record_authentication_event(request, 'api_logout_success', user=request.user)
        return Response({'message': 'Logged out.'})

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def register(self, request):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        GuestProfile.objects.get_or_create(user=user)
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserProfileSerializer(user).data,
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def me(self, request):
        return Response(UserProfileSerializer(request.user).data)

    @action(detail=False, methods=['put', 'patch'])
    def update_me(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data,
                                           partial=request.method == 'PATCH')
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def duplicates(self, request):
        return Response(UserProfileSerializer(duplicate_guest_groups(), many=True).data)

    @action(detail=True, methods=['post'], url_path='merge-guest')
    def merge_guest(self, request, pk=None):
        try:
            history = merge_guest_accounts(
                primary_id=self.get_object().id,
                duplicate_id=int(request.data.get('duplicate_id')),
                actor=request.user, reason=request.data.get('reason', ''),
            )
        except (DjangoValidationError, ValueError, TypeError) as exc:
            raise ApiValidationError(getattr(exc, 'messages', [str(exc)])) from exc
        return Response({
            'merge_id': history.id,
            'primary': UserProfileSerializer(history.primary_guest).data,
            'duplicate_id': history.duplicate_guest_id,
            'transferred_counts': history.transferred_counts,
        })


class GuestProfileViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = GuestProfile.objects.select_related('user').order_by('id')
    serializer_class = GuestProfileSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {
        'list': {'admin', 'manager', 'receptionist'},
        'retrieve': {'admin', 'manager', 'receptionist'},
        'create': {'admin', 'manager', 'receptionist'},
        'update': {'admin', 'manager', 'receptionist'},
        'partial_update': {'admin', 'manager', 'receptionist'},
        'destroy': {'admin'},
    }
    filter_backends = [SearchFilter]
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'user__email']
