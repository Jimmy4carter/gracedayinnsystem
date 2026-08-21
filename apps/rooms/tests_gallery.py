from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import UserProfile

from .models import Room, RoomType, RoomTypeImage


class RoomGalleryPublicTests(TestCase):
    def setUp(self):
        self.room_type = RoomType.objects.create(
            name='Gallery Suite', description='A calm modern suite.',
            base_price='45000.00', max_occupancy=2,
        )
        self.room = Room.objects.create(number='G-101', room_type=self.room_type)
        self.hero = RoomTypeImage.objects.create(
            room_type=self.room_type, image='room_types/gallery/hero.jpg',
            alt_text='King bed beside a sunlit sitting area', caption='Suite bedroom',
            is_featured=True, is_published=True,
        )
        self.draft = RoomTypeImage.objects.create(
            room_type=self.room_type, image='room_types/gallery/draft.jpg',
            alt_text='Unapproved draft bathroom photograph', is_published=False,
        )

    def test_rooms_and_detail_use_published_accessible_gallery_without_drafts(self):
        home = self.client.get(reverse('frontend:public-home'))
        self.assertContains(home, self.hero.image.url)
        self.assertNotContains(home, self.draft.image.url)

        listing = self.client.get(reverse('frontend:public-rooms'))
        self.assertContains(listing, self.hero.image.url)
        self.assertContains(listing, self.hero.alt_text)
        self.assertNotContains(listing, self.draft.image.url)

        detail = self.client.get(reverse('frontend:public-room-detail', args=[self.room.id]))
        self.assertContains(detail, self.hero.image.url)
        self.assertContains(detail, self.hero.alt_text)
        self.assertNotContains(detail, self.draft.image.url)

    def test_only_one_featured_image_is_allowed_per_room_type(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoomTypeImage.objects.create(
                room_type=self.room_type, image='room_types/gallery/second.jpg',
                alt_text='Second room view', is_featured=True, is_published=True,
            )


class RoomGalleryApiTests(APITestCase):
    def setUp(self):
        self.room_type = RoomType.objects.create(name='API Gallery', base_price='30000.00')
        self.published = RoomTypeImage.objects.create(
            room_type=self.room_type, image='room_types/gallery/public.jpg',
            alt_text='Published room photograph', is_published=True,
        )
        self.draft = RoomTypeImage.objects.create(
            room_type=self.room_type, image='room_types/gallery/private.jpg',
            alt_text='Draft room photograph', is_published=False,
        )
        self.guest = UserProfile.objects.create_user('gallery-guest', password='pass', role='guest')
        self.manager = UserProfile.objects.create_user('gallery-manager', password='pass', role='manager')

    def _gallery(self, user):
        self.client.force_authenticate(user)
        response = self.client.get('/api/room-types/')
        self.assertEqual(response.status_code, 200)
        result = response.data['results'][0] if isinstance(response.data, dict) else response.data[0]
        return result['gallery']

    def test_guest_api_sees_only_published_images(self):
        self.assertEqual([item['id'] for item in self._gallery(self.guest)], [self.published.id])

    def test_manager_api_can_review_draft_images(self):
        self.assertEqual(
            {item['id'] for item in self._gallery(self.manager)},
            {self.published.id, self.draft.id},
        )
