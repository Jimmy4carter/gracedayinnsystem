import sys
import os
import django

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gracedayinn.settings.base')
django.setup()

from apps.accounts.models import UserProfile, GuestProfile

users_to_create = [
    {
        'username': 'admin_tester',
        'email': 'admin_tester@example.com',
        'password': 'Password123!',
        'role': 'admin',
        'is_staff': True,
        'is_superuser': True,
    },
    {
        'username': 'manager_tester',
        'email': 'manager_tester@example.com',
        'password': 'Password123!',
        'role': 'manager',
        'is_staff': True,
    },
    {
        'username': 'receptionist_tester',
        'email': 'receptionist_tester@example.com',
        'password': 'Password123!',
        'role': 'receptionist',
        'is_staff': True,
    },
    {
        'username': 'accountant_tester',
        'email': 'accountant_tester@example.com',
        'password': 'Password123!',
        'role': 'accountant',
        'is_staff': True,
    },
    {
        'username': 'housekeeper_tester',
        'email': 'housekeeper_tester@example.com',
        'password': 'Password123!',
        'role': 'housekeeping',
        'is_staff': True,
    },
    {
        'username': 'guest_tester',
        'email': 'guest_tester@example.com',
        'password': 'Password123!',
        'role': 'guest',
        'is_staff': False,
    },
]

print("Starting test user creation...")
for u in users_to_create:
    user, created = UserProfile.objects.get_or_create(
        username=u['username'],
        defaults={
            'email': u['email'],
            'role': u['role'],
            'is_staff': u.get('is_staff', False),
            'is_superuser': u.get('is_superuser', False),
            'is_active': True,
        }
    )
    if created:
        user.set_password(u['password'])
        user.save()
        print(f"Created user: {user.username} with role {user.role}")
    else:
        # Update details/password to be sure
        user.email = u['email']
        user.role = u['role']
        user.is_staff = u.get('is_staff', False)
        user.is_superuser = u.get('is_superuser', False)
        user.set_password(u['password'])
        user.is_active = True
        user.save()
        print(f"Updated existing user: {user.username} with role {user.role}")

    # Ensure profiles exist
    if user.role == 'guest':
        GuestProfile.objects.get_or_create(user=user)

print("All test users created and initialized successfully.")
