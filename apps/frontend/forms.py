from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils import timezone
from django.db.models import Q
from django.core.exceptions import ValidationError

from apps.accounts.models import GuestProfile, UserProfile
from apps.billing.models import Invoice
from apps.housekeeping.models import HousekeepingTask
from apps.payments.models import Payment
from apps.reservations.models import Reservation
from apps.rooms.models import Amenity, Room, RoomType
from apps.services.models import MenuItem, ServiceOrder, ServiceOrderItem
from apps.frontend.models import NewsletterMessage


class NewsletterMessageForm(forms.ModelForm):
    class Meta:
        model = NewsletterMessage
        fields = [
            'subject',
            'title',
            'message',
            'cta_text',
            'cta_link',
            'featured_image',
            'recipient',
            'status',
        ]
        widgets = {
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Exclusive Weekend Offer at GRACEDAY INN'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Experience Luxury at GRACEDAY INN'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 6, 'placeholder': 'Treat yourself to a relaxing stay at GRACEDAY INN...'}),
            'cta_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Book Your Stay'}),
            'cta_link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': '/rooms/'}),
            'recipient': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
        help_texts = {
            'cta_link': 'Use an internal or external booking link.',
        }



class GuestCreateForm(forms.ModelForm):
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Leave blank to send an invite later'}),
    )

    class Meta:
        model = UserProfile
        fields = ('username', 'email', 'first_name', 'last_name', 'phone')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. guest_ada'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'guest@example.com'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone'}),
        }

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not username:
            raise forms.ValidationError('Username is required.')
        if UserProfile.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('A user with this username already exists.')
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise forms.ValidationError('Email is required.')
        if UserProfile.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('A user with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'guest'
        user.is_active = True
        raw_password = self.cleaned_data.get('password')
        if raw_password:
            user.set_password(raw_password)
        else:
            user.set_unusable_password()
        if commit:
            user.save()
            GuestProfile.objects.get_or_create(user=user)
        return user


class PortalLoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}))


class PortalSignUpForm(UserCreationForm):
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}))
    first_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'}))
    last_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'}))
    phone = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone'}))

    class Meta:
        model = UserProfile
        fields = ('username', 'first_name', 'last_name', 'email', 'phone', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ('username', 'password1', 'password2'):
            self.fields[field_name].widget.attrs['class'] = 'form-control'

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'guest'
        if commit:
            user.save()
        return user


class BookingRequestForm(forms.Form):
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    check_in_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    check_out_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    room = forms.ModelChoiceField(
        queryset=Room.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    num_adults = forms.IntegerField(min_value=1, initial=1, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    num_children = forms.IntegerField(min_value=0, initial=0, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    special_requests = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Any special requests?'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in_date')
        check_out = cleaned_data.get('check_out_date')
        room = cleaned_data.get('room')

        if check_in and check_in < timezone.localdate():
            self.add_error('check_in_date', 'Check-in date cannot be in the past.')

        if check_in and check_out and check_out <= check_in:
            self.add_error('check_out_date', 'Check-out date must be after check-in date.')

        if room and check_in and check_out:
            conflict_exists = Reservation.objects.filter(
                room=room,
                status__in=['pending', 'confirmed', 'checked_in'],
                check_in_date__lt=check_out,
                check_out_date__gt=check_in,
            ).exists()
            if conflict_exists:
                self.add_error('room', 'This room is unavailable for the selected dates.')

        return cleaned_data

    def create_reservation(self, request_user=None):
        data = self.cleaned_data
        user = request_user if request_user and request_user.is_authenticated else self._get_or_create_guest_user()
        reservation = Reservation.objects.create(
            guest=user,
            room=data['room'],
            check_in_date=data['check_in_date'],
            check_out_date=data['check_out_date'],
            num_adults=data['num_adults'],
            num_children=data['num_children'],
            special_requests=data['special_requests'],
            nightly_rate=data['room'].current_price,
            status='pending',
            notes=f"Requested via website. Contact: {data['phone'] or 'N/A'}",
            created_by=user,
        )
        return reservation

    def _get_or_create_guest_user(self):
        email = self.cleaned_data['email'].lower().strip()
        first_name = self.cleaned_data['first_name'].strip()
        last_name = self.cleaned_data['last_name'].strip()
        phone = self.cleaned_data['phone'].strip()

        user = UserProfile.objects.filter(email=email).first()
        if user:
            user.first_name = first_name
            user.last_name = last_name
            if phone:
                user.phone = phone
            user.save(update_fields=['first_name', 'last_name', 'phone'])
            return user

        base_username = email.split('@')[0] or 'guest'
        username = base_username
        index = 1
        while UserProfile.objects.filter(username=username).exists():
            username = f'{base_username}{index}'
            index += 1

        user = UserProfile.objects.create(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role='guest',
            is_active=True,
        )
        user.set_unusable_password()
        user.save(update_fields=['password'])
        return user


class ContactForm(forms.Form):
    name = forms.CharField(max_length=120, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    subject = forms.CharField(max_length=200, widget=forms.TextInput(attrs={'class': 'form-control'}))
    message = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}))


ABOUT_PAGE_AMENITY_SUGGESTIONS = [
    ('Free WiFi', 'Free WiFi', 'Enjoy fast and reliable internet access throughout the hotel premises.', 'flaticon-029-wifi'),
    ('Air Conditioning', 'Air Conditioning', 'All rooms are fully air-conditioned for maximum guest comfort.', 'flaticon-003-air-conditioner'),
    ('Smart TV', 'Smart TV', 'Enjoy premium entertainment and satellite television channels.', 'flaticon-019-television'),
    ('Laundry', 'Laundry', 'Enjoy clean and fresh clothing from our high-quality laundry service.', 'flaticon-004-fridge'),
    ('Secure Safe', 'Secure Safe', 'Keep valuables protected using our secure in-room safety locker.', 'flaticon-013-safety-box'),
    ('Luxury Bathtub', 'Luxury Bathtub', 'Relax in spacious bathrooms with premium bathtub facilities.', 'flaticon-030-bathtub'),
    ('24-Hour Service', '24-Hour Service', 'Round-the-clock hospitality support and assistance for every guest.', 'flaticon-026-bed'),
    ('Dining Service', 'Dining Service', 'Enjoy convenient dining options and room service support throughout the day.', 'flaticon-004-fridge'),
]


class RoomCreateForm(forms.ModelForm):
    amenities = forms.ModelMultipleChoiceField(
        queryset=Amenity.objects.order_by('name'),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
    )

    class Meta:
        model = Room
        fields = ['number', 'room_type', 'floor', 'status', 'description', 'notes', 'is_active']
        widgets = {
            'number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 205'}),
            'room_type': forms.Select(attrs={'class': 'form-select'}),
            'floor': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['room_type'].queryset = RoomType.objects.order_by('name')
        self.fields['room_type'].empty_label = 'Select room type'
        self.fields['is_active'].required = False

    def save(self, commit=True):
        room = super().save(commit=False)
        if commit:
            room.save()
        selected_amenities = list(self.cleaned_data.get('amenities', []))
        if room.room_type_id and selected_amenities:
            room.room_type.amenities.set(selected_amenities)
        if commit:
            room.room_type.refresh_from_db()
        return room


class AmenityCreateForm(forms.ModelForm):
    preset = forms.ChoiceField(
        choices=[('', 'Create a custom amenity')] + [(name, label) for name, label, _, _ in ABOUT_PAGE_AMENITY_SUGGESTIONS],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = Amenity
        fields = ['name', 'icon', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Spa Access'}),
            'icon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. flaticon-029-wifi'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = False
        self.fields['icon'].required = False

    def save(self, commit=True):
        amenity = super().save(commit=False)
        preset = self.cleaned_data.get('preset')
        if preset:
            _, label, description, icon = next(item for item in ABOUT_PAGE_AMENITY_SUGGESTIONS if item[0] == preset)
            amenity.name = label
            amenity.icon = icon
            amenity.description = description
        else:
            amenity.name = amenity.name or ''
        if commit:
            amenity.save()
        return amenity


class PortalReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = [
            'guest',
            'room',
            'check_in_date',
            'check_out_date',
            'num_adults',
            'num_children',
            'special_requests',
        ]
        widgets = {
            'guest': forms.Select(attrs={'class': 'form-select'}),
            'room': forms.Select(attrs={'class': 'form-select'}),
            'check_in_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'check_out_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'num_adults': forms.NumberInput(attrs={'class': 'form-control'}),
            'num_children': forms.NumberInput(attrs={'class': 'form-control'}),
            'special_requests': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['guest'].queryset = UserProfile.objects.filter(role='guest', is_active=True).order_by('username')
        self.fields['room'].queryset = Room.objects.filter(is_active=True).select_related('room_type').order_by('number')

    def clean(self):
        cleaned_data = super().clean()
        room = cleaned_data.get('room')
        check_in = cleaned_data.get('check_in_date')
        check_out = cleaned_data.get('check_out_date')

        if check_in and check_out and check_out <= check_in:
            self.add_error('check_out_date', 'Check-out must be after check-in.')

        if room and check_in and check_out:
            overlap_exists = Reservation.objects.filter(
                room=room,
                status__in=['pending', 'confirmed', 'checked_in'],
                check_in_date__lt=check_out,
                check_out_date__gt=check_in,
            ).exists()
            if overlap_exists:
                self.add_error('room', 'The selected room is not available for these dates.')

        return cleaned_data

    def save(self, commit=True):
        reservation = super().save(commit=False)
        reservation.status = reservation.status or 'pending'
        reservation.nightly_rate = reservation.room.current_price
        if commit:
            reservation.save()
        return reservation


class PaymentRecordForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['invoice', 'amount', 'method', 'transaction_id', 'status', 'notes']
        widgets = {
            'invoice': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'method': forms.Select(attrs={'class': 'form-select'}),
            'transaction_id': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        invoices_qs = Invoice.objects.select_related('guest').exclude(status='cancelled').order_by('-created_at')
        if user and user.role == 'guest':
            invoices_qs = invoices_qs.filter(guest=user)
        self.fields['invoice'].queryset = invoices_qs

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError('Payment amount must be greater than zero.')
        return amount


class ServiceOrderCreateForm(forms.Form):
    # accept a plain-text guest identifier (username or email) instead of a dropdown
    guest = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'username or email'}))
    room = forms.ModelChoiceField(
        queryset=Room.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    menu_item = forms.ModelChoiceField(
        queryset=MenuItem.objects.filter(is_available=True).select_related('category'),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    quantity = forms.IntegerField(min_value=1, initial=1, widget=forms.NumberInput(attrs={'class': 'form-control'}))

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and user.role == 'guest':
            self.fields['guest'].initial = user.username

    def clean_guest(self):
        raw = (self.cleaned_data.get('guest') or '').strip()
        if not raw:
            raise ValidationError('Guest username or email is required.')

        user = UserProfile.objects.filter(
            Q(username__iexact=raw) | Q(email__iexact=raw),
            role='guest',
            is_active=True,
        ).first()

        if not user:
            raise ValidationError('No active guest found with that username or email.')

        return user

    def save(self, created_by):
        order = ServiceOrder.objects.create(
            guest=self.cleaned_data['guest'],
            room=self.cleaned_data.get('room'),
            notes='',
            status='pending',
        )
        ServiceOrderItem.objects.create(
            order=order,
            menu_item=self.cleaned_data['menu_item'],
            quantity=self.cleaned_data['quantity'],
            unit_price=self.cleaned_data['menu_item'].price,
        )
        order.recalculate_total()
        return order


class HousekeepingTaskCreateForm(forms.ModelForm):
    class Meta:
        model = HousekeepingTask
        fields = ['room', 'task_type', 'priority', 'assigned_to', 'scheduled_at', 'notes']
        widgets = {
            'room': forms.Select(attrs={'class': 'form-select'}),
            'task_type': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'scheduled_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['room'].queryset = Room.objects.filter(is_active=True).order_by('number')
        self.fields['assigned_to'].queryset = UserProfile.objects.filter(
            role__in=['housekeeping', 'manager', 'admin'],
            is_active=True,
        ).order_by('username')
class ContactForm(forms.Form):
    name = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your Name'
        })
    )

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your Email'
        })
    )

    subject = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Subject'
        })
    )

    message = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Type your message here...'
        })
    )