from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Create initial hotel data (rooms, amenities, services)'

    def handle(self, *args, **options):
        self.stdout.write('Creating initial data...')
        self._create_superuser()
        self._create_amenities()
        self._create_room_types()
        self._create_rooms()
        self._create_service_categories()
        self.stdout.write(self.style.SUCCESS('Initial data created successfully!'))

    def _create_superuser(self):
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='admin@gracedayinn.com',
                password='admin123',
                role='admin',
                first_name='Admin',
                last_name='User',
            )
            self.stdout.write('  Created superuser: admin / admin123')

    def _create_amenities(self):
        from apps.rooms.models import Amenity
        amenities = [
            ('WiFi', '📶'), ('Air Conditioning', '❄️'), ('TV', '📺'),
            ('Laundry', '🍷'), ('Conference Room', '🔒'), ('Bathtub', '🛁'),
            ('Scenic Views', '🌊'), ('Balcony', '🏖️'), ('Coffee Maker', '☕'),
            ('Iron & Board', '👔'), ('Room Service', '🍽️'),
        ]
        for name, icon in amenities:
            Amenity.objects.get_or_create(name=name, defaults={'icon': icon})
        self.stdout.write(f'  Created {len(amenities)} amenities')

    def _create_room_types(self):
        from apps.rooms.models import RoomType, Amenity
        wifi = Amenity.objects.get(name='WiFi')
        ac = Amenity.objects.get(name='Air Conditioning')
        tv = Amenity.objects.get(name='TV')
        room_types = [
            ('Standard Room', 89.00, 2, [wifi, ac, tv]),
            ('Deluxe Room', 149.00, 2, [wifi, ac, tv]),
            ('Suite', 249.00, 4, [wifi, ac, tv]),
            ('Presidential Suite', 499.00, 6, [wifi, ac, tv]),
            ('Family Room', 179.00, 5, [wifi, ac, tv]),
        ]
        for name, price, occ, ams in room_types:
            rt, _ = RoomType.objects.get_or_create(
                name=name,
                defaults={'base_price': price, 'max_occupancy': occ}
            )
            rt.amenities.set(ams)
        self.stdout.write(f'  Created {len(room_types)} room types')

    def _create_rooms(self):
        from apps.rooms.models import Room, RoomType
        standard = RoomType.objects.get(name='Standard Room')
        deluxe = RoomType.objects.get(name='Deluxe Room')
        suite = RoomType.objects.get(name='Suite')
        presidential = RoomType.objects.get(name='Presidential Suite')
        family = RoomType.objects.get(name='Family Room')

        rooms_data = []
        # Floors 1-4: standard
        for floor in range(1, 5):
            for num in range(1, 11):
                rooms_data.append((f'{floor}{num:02d}', standard, floor))
        # Floors 2-3: deluxe
        for floor in range(2, 4):
            for num in range(11, 21):
                rooms_data.append((f'{floor}{num:02d}', deluxe, floor))
        # Floor 4: suites
        for num in range(1, 6):
            rooms_data.append((f'4{num:02d}S', suite, 4))
        # Family rooms
        for num in range(1, 4):
            rooms_data.append((f'5{num:02d}F', family, 5))
        # Presidential suite
        rooms_data.append(('PRES', presidential, 6))

        created = 0
        for number, rt, floor in rooms_data:
            _, is_new = Room.objects.get_or_create(
                number=number,
                defaults={'room_type': rt, 'floor': floor}
            )
            if is_new:
                created += 1
        self.stdout.write(f'  Created {created} rooms')

    def _create_service_categories(self):
        from apps.services.models import ServiceCategory, MenuItem
        categories = [
            ('Room Service', '🍽️', [
                ('Club Sandwich', 18.00), ('Caesar Salad', 14.00),
                ('Grilled Chicken', 24.00), ('Pasta Carbonara', 20.00),
            ]),
            ('Beverages', '🍹', [
                ('Orange Juice', 6.00), ('Coffee', 5.00),
                ('Smoothie', 9.00), ('Bottled Water', 3.00),
            ]),
            ('Spa & Wellness', '💆', [
                ('60-min Massage', 80.00), ('Facial Treatment', 65.00),
            ]),
            ('Laundry', '👔', [
                ('Shirt Wash', 5.00), ('Suit Dry Clean', 15.00),
            ]),
        ]
        for cat_name, icon, items in categories:
            cat, _ = ServiceCategory.objects.get_or_create(
                name=cat_name,
                defaults={'icon': icon}
            )
            for item_name, price in items:
                MenuItem.objects.get_or_create(
                    name=item_name,
                    category=cat,
                    defaults={'price': price}
                )
        self.stdout.write(f'  Created {len(categories)} service categories with menu items')
