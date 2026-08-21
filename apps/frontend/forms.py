from django import forms
import uuid
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils import timezone
from django.db.models import Q
from django.core.exceptions import ValidationError

from apps.accounts.models import GuestProfile, UserProfile, normalize_guest_email
from apps.billing.models import Invoice
from apps.housekeeping.models import (
    HousekeepingTask, IncidentReport, LostFoundItem, MaintenanceTicket,
    StockItem, StockLocation,
)
from apps.payments.models import Payment
from apps.reservations.models import Reservation
from apps.reservations.services import create_reservation
from apps.rooms.models import Amenity, BookableExtra, Room, RoomType
from apps.services.models import MenuItem, ServiceOrder, ServiceOrderItem
from apps.frontend.models import NewsletterMessage


class GuestModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        name = obj.get_full_name() or obj.username
        contact = f" ({obj.email})" if obj.email else ""
        phone = f" | {obj.phone}" if obj.phone else ""
        return f"{name}{contact}{phone}"


class RoomModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        rtype = obj.room_type.name if obj.room_type else "Room"
        price = f"₦{obj.current_price:,.2f}"
        status = obj.get_status_display()
        return f"Room {obj.number} ({rtype}) — {price}/night [{status}]"


class InvoiceModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        guest_name = obj.guest.get_full_name() if obj.guest else (obj.guest.username if obj.guest else "Guest")
        total = f"₦{obj.total:,.2f}"
        balance = f"₦{obj.balance:,.2f}"
        status = obj.get_status_display().upper()
        res_num = f" (Res #{obj.reservation.reservation_number})" if obj.reservation else ""
        return f"Invoice #{obj.invoice_number}{res_num} — {guest_name} — Total: {total} (Due: {balance}) [{status}]"


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
        if UserProfile.objects.filter(normalized_email=normalize_guest_email(email), merged_into__isnull=True).exists():
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

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if UserProfile.objects.filter(
            normalized_email=normalize_guest_email(email), merged_into__isnull=True,
        ).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'guest'
        if commit:
            user.save()
        return user


class RoomSearchForm(forms.Form):
    check_in_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    check_out_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    num_adults = forms.IntegerField(
        min_value=1, initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1})
    )
    num_children = forms.IntegerField(
        min_value=0, initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0})
    )
    room_type = forms.ModelChoiceField(
        queryset=RoomType.objects.all(),
        required=False,
        empty_label='All room types',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in_date')
        check_out = cleaned_data.get('check_out_date')

        if check_in and check_in < timezone.localdate():
            self.add_error('check_in_date', 'Check-in date cannot be in the past.')

        if check_in and check_out and check_out <= check_in:
            self.add_error('check_out_date', 'Check-out date must be after check-in date.')

        return cleaned_data


class BookingRequestForm(forms.Form):
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'given-name'}))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'family-name'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email'}))
    phone = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'tel'}))
    check_in_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    check_out_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    room = forms.ModelChoiceField(
        queryset=Room.objects.filter(is_active=True, is_sellable=True),
        widget=forms.HiddenInput(),
    )
    num_adults = forms.IntegerField(min_value=1, initial=1, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    num_children = forms.IntegerField(min_value=0, initial=0, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    special_requests = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Any special requests?'}),
    )
    promotion_code = forms.CharField(
        max_length=50, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off', 'placeholder': 'Optional offer code'}),
    )
    extras = forms.ModelMultipleChoiceField(
        queryset=BookableExtra.objects.filter(is_active=True), required=False,
        widget=forms.CheckboxSelectMultiple,
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
            elif room.inventory_blocks.filter(
                status='active', start_date__lt=check_out, end_date__gt=check_in
            ).exists():
                self.add_error('room', 'This room is blocked from sale for the selected dates.')

        return cleaned_data

    def create_reservation(self, request_user=None):
        data = self.cleaned_data
        user = request_user if request_user and request_user.is_authenticated else self._get_or_create_guest_user()
        reservation = create_reservation(
            guest=user,
            room=data['room'],
            check_in_date=data['check_in_date'],
            check_out_date=data['check_out_date'],
            num_adults=data['num_adults'],
            num_children=data['num_children'],
            special_requests=data['special_requests'],
            notes=f"Requested via website. Contact: {data['phone'] or 'N/A'}",
            created_by=user,
            source='direct_website',
        )
        return reservation

    def _get_or_create_guest_user(self):
        email = self.cleaned_data['email'].lower().strip()
        first_name = self.cleaned_data['first_name'].strip()
        last_name = self.cleaned_data['last_name'].strip()
        phone = self.cleaned_data['phone'].strip()

        user = UserProfile.objects.filter(
            normalized_email=normalize_guest_email(email), merged_into__isnull=True,
        ).first()
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
        user.set_unusable_password()
        user.save(update_fields=['password'])
        return user


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


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(item, initial) for item in data]
        return single(data, initial)


class RoomCreateForm(forms.ModelForm):
    gallery_images = MultipleFileField(required=False, widget=MultipleFileInput(attrs={'class': 'form-control', 'multiple': True, 'accept': 'image/*'}))
    class Meta:
        model = Room
        fields = ['number', 'room_type', 'floor', 'status', 'price', 'image', 'amenities', 'description', 'notes', 'is_active', 'is_sellable']
        widgets = {
            'number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 205'}),
            'room_type': forms.Select(attrs={'class': 'form-select'}),
            'floor': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Optional custom price'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'amenities': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_sellable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['room_type'].queryset = RoomType.objects.order_by('name')
        self.fields['room_type'].empty_label = 'Select room type'
        self.fields['is_active'].required = False
        self.fields['is_sellable'].required = False
        self.fields['amenities'].queryset = Amenity.objects.order_by('name')
        self.fields['amenities'].required = False

    def save(self, commit=True):
        room = super().save(commit=False)
        if commit:
            room.save()
            self.save_m2m()
        return room


class RoomTypeCreateForm(forms.ModelForm):
    class Meta:
        model = RoomType
        fields = ['name', 'slug', 'description', 'base_price', 'max_occupancy', 'amenities', 'image']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Deluxe Studio'}),
            'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'auto-generated if blank'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'base_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'max_occupancy': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'amenities': forms.CheckboxSelectMultiple(),
            'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['amenities'].queryset = Amenity.objects.order_by('name')


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


class StaffCreateForm(forms.ModelForm):
    password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Initial password'}),
    )
    role = forms.ChoiceField(
        choices=[
            ('admin', 'Admin'),
            ('manager', 'Manager'),
            ('receptionist', 'Receptionist'),
            ('accountant', 'Accountant'),
            ('housekeeping', 'Housekeeping'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = UserProfile
        fields = ('username', 'email', 'first_name', 'last_name', 'phone', 'role')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. staff_john'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'staff@gracedayinn.com'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'}),
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
        if UserProfile.objects.filter(normalized_email=normalize_guest_email(email)).exists():
            raise forms.ValidationError('A user with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = True
        user.is_staff = True
        if user.role == 'admin':
            user.is_superuser = True
        raw_password = self.cleaned_data.get('password')
        if raw_password:
            user.set_password(raw_password)
        if commit:
            user.save()
        return user


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
        guest_qs = UserProfile.objects.filter(role='guest', is_active=True).order_by('first_name', 'username')
        room_qs = Room.objects.filter(is_active=True).select_related('room_type').order_by('number')
        self.fields['guest'] = GuestModelChoiceField(queryset=guest_qs, widget=forms.Select(attrs={'class': 'form-select'}))
        self.fields['room'] = RoomModelChoiceField(queryset=room_qs, widget=forms.Select(attrs={'class': 'form-select'}))

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
    idempotency_key = forms.CharField(widget=forms.HiddenInput(), initial=uuid.uuid4)

    class Meta:
        model = Payment
        fields = ['invoice', 'amount', 'method', 'transaction_id', 'notes']
        widgets = {
            'invoice': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'method': forms.Select(attrs={'class': 'form-select'}),
            'transaction_id': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        invoices_qs = Invoice.objects.select_related('guest', 'reservation').exclude(status='cancelled').order_by('-created_at')
        if user and user.role == 'guest':
            invoices_qs = invoices_qs.filter(guest=user)
        self.fields['invoice'] = InvoiceModelChoiceField(queryset=invoices_qs, widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_payment_invoice'}))

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


class MaintenanceTicketCreateForm(forms.ModelForm):
    class Meta:
        model = MaintenanceTicket
        fields = [
            'room', 'title', 'category', 'priority', 'description',
            'downtime_required', 'assigned_to', 'estimated_cost', 'evidence',
        ]
        widgets = {
            'room': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.TextInput(attrs={'class': 'form-control'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'downtime_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'estimated_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'evidence': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['room'].queryset = Room.objects.filter(is_active=True).order_by('number')
        self.fields['assigned_to'].queryset = UserProfile.objects.filter(
            role__in=['housekeeping', 'manager', 'admin'], is_active=True,
        ).order_by('username')


class IncidentReportCreateForm(forms.ModelForm):
    class Meta:
        model = IncidentReport
        fields = [
            'incident_type', 'severity', 'title', 'description', 'location',
            'occurred_at', 'room', 'reservation', 'assigned_to',
        ]
        widgets = {
            'incident_type': forms.Select(attrs={'class': 'form-select'}),
            'severity': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'occurred_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'room': forms.Select(attrs={'class': 'form-select'}),
            'reservation': forms.Select(attrs={'class': 'form-select'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['room'].queryset = Room.objects.filter(is_active=True).order_by('number')
        self.fields['reservation'].queryset = Reservation.objects.exclude(
            status='cancelled'
        ).select_related('guest').order_by('-created_at')
        self.fields['assigned_to'].queryset = UserProfile.objects.filter(
            role__in=['admin', 'manager', 'receptionist'], is_active=True,
        ).order_by('username')

    def clean(self):
        data = super().clean()
        if data.get('room') and data.get('reservation') and data['reservation'].room_id != data['room'].id:
            self.add_error('reservation', 'The reservation must belong to the selected room.')
        return data


class LostFoundItemCreateForm(forms.ModelForm):
    class Meta:
        model = LostFoundItem
        fields = ['item_name', 'description', 'found_location', 'found_at', 'room']
        widgets = {
            'item_name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'found_location': forms.TextInput(attrs={'class': 'form-control'}),
            'found_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'room': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['room'].queryset = Room.objects.filter(is_active=True).order_by('number')


class StockMovementForm(forms.Form):
    MOVEMENT_CHOICES = [
        ('receipt', 'Receive stock'), ('issue', 'Issue stock'), ('waste', 'Record waste'),
        ('adjustment_add', 'Positive adjustment'), ('adjustment_remove', 'Negative adjustment'),
        ('transfer', 'Transfer between locations'),
    ]
    item = forms.ModelChoiceField(queryset=StockItem.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}))
    location = forms.ModelChoiceField(queryset=StockLocation.objects.none(), label='Source / location', widget=forms.Select(attrs={'class': 'form-select'}))
    destination = forms.ModelChoiceField(queryset=StockLocation.objects.none(), required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    movement_type = forms.ChoiceField(choices=MOVEMENT_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    quantity = forms.DecimalField(min_value=0.001, decimal_places=3, max_digits=14, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}))
    reason = forms.CharField(max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'}))
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput(), initial=uuid.uuid4)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        items = StockItem.objects.filter(is_active=True)
        if user and user.role == 'housekeeping':
            items = items.filter(category__in=['linen', 'housekeeping'])
        elif user and user.role == 'receptionist':
            items = items.filter(category__in=['minibar', 'other'])
        self.fields['item'].queryset = items.order_by('category', 'name')
        locations = StockLocation.objects.filter(is_active=True).order_by('name')
        self.fields['location'].queryset = locations
        self.fields['destination'].queryset = locations
        if user and user.role not in {'admin', 'manager'}:
            self.fields['movement_type'].choices = [
                choice for choice in self.MOVEMENT_CHOICES if choice[0] in {'issue', 'waste', 'transfer'}
            ]

    def clean(self):
        data = super().clean()
        if data.get('movement_type') == 'transfer':
            if not data.get('destination'):
                self.add_error('destination', 'A destination is required for transfers.')
            elif data.get('location') == data.get('destination'):
                self.add_error('destination', 'Destination must differ from the source.')
        return data

class ContactForm(forms.Form):
    category = forms.ChoiceField(
        choices=[
            ('reservation', 'Reservation'), ('corporate', 'Corporate/Group'),
            ('event', 'Event'), ('service', 'Service'), ('billing', 'Billing'),
            ('complaint', 'Complaint'), ('general', 'General'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
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
