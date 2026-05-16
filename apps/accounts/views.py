from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import UserProfile, GuestProfile
from .serializers import (UserProfileSerializer, UserCreateSerializer,
                          LoginSerializer, GuestProfileSerializer)


class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['role', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']

    def get_serializer_class(self):
        if self.action in ('create',):
            return UserCreateSerializer
        return UserProfileSerializer

    def get_permissions(self):
        if self.action in ('create', 'login', 'register'):
            return [permissions.AllowAny()]
        return super().get_permissions()

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def login(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserProfileSerializer(user).data,
        })

    @action(detail=False, methods=['post'])
    def logout(self, request):
        try:
            token = RefreshToken(request.data.get('refresh'))
            token.blacklist()
        except Exception:
            pass
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


class GuestProfileViewSet(viewsets.ModelViewSet):
    queryset = GuestProfile.objects.select_related('user').all()
    serializer_class = GuestProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [SearchFilter]
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'user__email']
