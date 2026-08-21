from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import UserProfile, GuestProfile
from .security import login_is_blocked, record_authentication_event, record_login_failure
from .mfa import staff_mfa_required, verify_mfa_code
from .models import StaffMFADevice


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role',
                  'phone', 'avatar', 'address', 'id_type', 'id_last_four', 'nationality',
                  'date_joined', 'is_active', 'merged_into', 'merged_at',
                  'privacy_legal_hold', 'anonymized_at']
        read_only_fields = [
            'role', 'date_joined', 'merged_into', 'merged_at',
            'privacy_legal_hold', 'anonymized_at',
        ]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = UserProfile
        fields = ['username', 'email', 'first_name', 'last_name', 'role',
                  'phone', 'password', 'password_confirm']

    def validate(self, data):
        if data['password'] != data.pop('password_confirm'):
            raise serializers.ValidationError('Passwords do not match.')
        request = self.context.get('request')
        requested_role = data.get('role', 'guest')
        if not request or not request.user.is_authenticated:
            if requested_role != 'guest':
                raise serializers.ValidationError({'role': 'Public registration can only create guest accounts.'})
            data['role'] = 'guest'
        elif not request.user.is_superuser and request.user.role != 'admin':
            raise serializers.ValidationError({'role': 'Only administrators can assign account roles.'})
        return data

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = UserProfile(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    mfa_code = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate(self, data):
        request = self.context.get('request')
        if request and login_is_blocked(request, data['username']):
            record_authentication_event(request, 'api_login_blocked', username=data['username'])
            raise serializers.ValidationError('Unable to sign in. Please wait and try again.')
        user = authenticate(username=data['username'], password=data['password'])
        if not user:
            if request:
                record_login_failure(request, data['username'])
                record_authentication_event(request, 'api_login_failed', username=data['username'])
            raise serializers.ValidationError('Invalid credentials.')
        if not user.is_active:
            raise serializers.ValidationError('Account is disabled.')
        if staff_mfa_required(user):
            if not StaffMFADevice.objects.filter(user=user, is_confirmed=True).exists():
                raise serializers.ValidationError({
                    'mfa_code': 'MFA enrollment is required in the staff portal before API login.',
                })
            if not data.get('mfa_code'):
                raise serializers.ValidationError({'mfa_code': 'An MFA code is required.'})
            try:
                verify_mfa_code(user=user, code=data['mfa_code'])
            except serializers.ValidationError:
                raise
            except Exception as exc:
                messages = getattr(exc, 'messages', [str(exc)])
                raise serializers.ValidationError({'mfa_code': messages}) from exc
        data['user'] = user
        return data


class GuestProfileSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)

    class Meta:
        model = GuestProfile
        fields = '__all__'
