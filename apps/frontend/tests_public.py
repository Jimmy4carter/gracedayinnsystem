from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    AnalyticsEvent, BillboardContent, FAQItem, FeatureFlag, GuestTestimonial, LocalGuidePlace,
    LocalGuidePlaceTranslation, SitePage, SitePageTranslation,
)


class PublicExperienceTests(TestCase):
    def test_billboard_renders_real_content_qr_and_status_feed(self):
        FAQItem.objects.create(
            category='stay', question='Can I request a late checkout?',
            answer='Please ask reception and we will check availability.', is_published=True,
        )
        BillboardContent.objects.create(
            title='Welcome home', subtitle='A GraceDay moment', body='Enjoy your stay.',
            content_type='brand', is_active=True,
        )
        response = self.client.get(reverse('frontend:public-billboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-graceday-tv')
        self.assertContains(response, 'Welcome home')
        self.assertContains(response, 'Can I request a late checkout?')
        self.assertContains(response, 'data:image/png;base64,')

        status = self.client.get(reverse('frontend:public-billboard'), {'status': '1'})
        self.assertEqual(status.status_code, 200)
        self.assertIn('version', status.json())

    def test_billboard_randomizes_a_small_cross_category_room_spotlight(self):
        from apps.rooms.models import Room, RoomType

        for category_index in range(7):
            room_type = RoomType.objects.create(
                name=f'Billboard type {category_index}', base_price='50000.00', max_occupancy=2
            )
            for room_index in range(3):
                Room.objects.create(
                    number=f'BB-{category_index}-{room_index}', room_type=room_type
                )

        response = self.client.get(reverse('frontend:public-billboard'))

        self.assertEqual(len(response.context['rooms']), 5)
        self.assertEqual(len({room.room_type_id for room in response.context['rooms']}), 5)
        self.assertEqual(response.content.count(b'data-category="room"'), 5)

    def test_billboard_excludes_inactive_and_out_of_window_content(self):
        now = timezone.now()
        BillboardContent.objects.create(
            title='Currently showing', content_type='information', is_active=True,
            start_at=now - timedelta(hours=1), end_at=now + timedelta(hours=1),
        )
        BillboardContent.objects.create(
            title='Future campaign', content_type='promotion', is_active=True,
            start_at=now + timedelta(days=1),
        )
        BillboardContent.objects.create(
            title='Disabled campaign', content_type='promotion', is_active=False,
        )
        response = self.client.get(reverse('frontend:public-billboard'))
        self.assertContains(response, 'Currently showing')
        self.assertNotContains(response, 'Future campaign')
        self.assertNotContains(response, 'Disabled campaign')

    def test_billboard_content_rejects_invalid_schedule(self):
        now = timezone.now()
        content = BillboardContent(
            title='Invalid campaign', content_type='promotion',
            start_at=now, end_at=now - timedelta(minutes=1),
        )
        with self.assertRaises(ValidationError):
            content.full_clean()

    def test_public_shell_has_accessibility_and_seo_basics(self):
        response = self.client.get(reverse('frontend:public-home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="skip-link"')
        self.assertContains(response, 'rel="canonical"')
        self.assertContains(response, 'application/ld+json')
        self.assertContains(response, 'Choose your dates and guest capacity')

    def test_robots_and_sitemap_expose_public_routes_only(self):
        robots = self.client.get(reverse('frontend:robots-txt'))
        self.assertContains(robots, 'Disallow: /portal/')
        self.assertContains(robots, '/sitemap.xml')
        sitemap = self.client.get(reverse('frontend:public-sitemap'))
        self.assertEqual(sitemap['Content-Type'], 'application/xml')
        self.assertContains(sitemap, 'http://testserver/rooms/')
        self.assertNotContains(sitemap, '/portal/')

    def test_published_page_content_overrides_home_hero_and_metadata(self):
        SitePage.objects.create(
            path='/', navigation_title='Home', browser_title='Apo-Dutse Hotel',
            meta_description='A locally managed stay in Abuja.', hero_title='Rest well in Abuja',
            hero_summary='A quieter stay close to the city.', is_published=True,
        )
        response = self.client.get(reverse('frontend:public-home'))
        self.assertContains(response, '<title>Apo-Dutse Hotel</title>', html=True)
        self.assertContains(response, 'Rest well in Abuja')
        self.assertContains(response, 'A quieter stay close to the city.')

    def test_room_detail_uses_guest_dates_not_room_record_timestamps(self):
        from apps.rooms.models import Room, RoomType

        room_type = RoomType.objects.create(name='Test Room', base_price='100.00', max_occupancy=2)
        room = Room.objects.create(number='PUBLIC-1', room_type=room_type)
        response = self.client.get(reverse('frontend:public-room-detail', args=[room.pk]))
        self.assertContains(response, 'name="check_in_date"')
        self.assertContains(response, 'name="check_out_date"')
        self.assertContains(response, f'name="room" value="{room.pk}"')
        self.assertNotContains(response, 'Brandon Kelley')

    def test_public_booking_shows_itemized_quote_before_email_verification(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.rooms.models import Room, RoomType, TaxFee

        room_type = RoomType.objects.create(name='Quote Room', base_price='10000.00', max_occupancy=2)
        room = Room.objects.create(number='QUOTE-1', room_type=room_type)
        TaxFee.objects.create(name='Hotel tax', code='hotel-tax', calculation='percentage', amount='5.00')
        arrival = timezone.localdate() + timedelta(days=10)
        response = self.client.post(reverse('frontend:public-room-detail', args=[room.pk]), {
            'first_name': 'Quote', 'last_name': 'Guest', 'email': 'quote@example.com',
            'phone': '08000000000', 'check_in_date': arrival,
            'check_out_date': arrival + timedelta(days=2), 'room': room.id,
            'num_adults': 1, 'num_children': 0, 'special_requests': '', 'promotion_code': '',
        })
        self.assertRedirects(response, reverse('frontend:public-quote-confirm'), fetch_redirect_response=False)
        review = self.client.get(reverse('frontend:public-quote-confirm'))
        self.assertContains(review, 'Accommodation subtotal')
        self.assertContains(review, 'Hotel tax')
        self.assertContains(review, 'NGN 21,000.00')
        self.assertTrue(AnalyticsEvent.objects.filter(event_name='quote_view').exists())

    def test_booking_feature_flag_can_disable_public_checkout(self):
        from apps.rooms.models import Room, RoomType
        room_type = RoomType.objects.create(name='Test Room', base_price='10000.00', max_occupancy=2)
        room = Room.objects.create(number='FLAG-1', room_type=room_type)
        FeatureFlag.objects.update_or_create(
            key='public-booking', defaults={'description': 'Booking', 'is_enabled': False}
        )
        response = self.client.post(reverse('frontend:public-room-detail', args=[room.pk]), {})
        self.assertRedirects(response, reverse('frontend:public-contact'), fetch_redirect_response=False)
        self.assertTrue(AnalyticsEvent.objects.filter(
            event_name='booking_error', metadata__error_code='feature_disabled'
        ).exists())

    def test_local_guide_only_displays_published_places_and_approved_consented_reviews(self):
        published = LocalGuidePlace.objects.create(
            name='Abuja Arts Centre', category='landmark', summary='Local arts and crafts.',
            travel_minutes=20, is_published=True,
        )
        LocalGuidePlace.objects.create(
            name='Draft recommendation', category='dining', summary='Not ready.', is_published=False,
        )
        GuestTestimonial.objects.create(
            display_name='Published Guest', rating=5, body='A comfortable stay.',
            publication_consent=True, status='approved',
        )
        GuestTestimonial.objects.create(
            display_name='Pending Guest', rating=3, body='Awaiting review.',
            publication_consent=True, status='pending',
        )
        response = self.client.get(reverse('frontend:public-guide'))
        self.assertContains(response, published.name)
        self.assertNotContains(response, 'Draft recommendation')
        self.assertContains(response, 'Published Guest')
        self.assertNotContains(response, 'Pending Guest')
        self.assertContains(response, 'aria-label="5 out of 5 stars"')

    def test_review_submission_requires_consent_and_enters_moderation_queue(self):
        response = self.client.post(reverse('frontend:public-guide'), {
            'display_name': 'Recent Guest', 'rating': '4', 'body': 'Helpful team.',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(GuestTestimonial.objects.exists())
        response = self.client.post(reverse('frontend:public-guide'), {
            'display_name': 'Recent Guest', 'rating': '4', 'body': 'Helpful team.',
            'publication_consent': 'on',
        })
        self.assertRedirects(response, reverse('frontend:public-guide'))
        item = GuestTestimonial.objects.get()
        self.assertEqual(item.status, 'pending')
        self.assertTrue(item.publication_consent)

    def test_published_translation_overrides_page_and_guide_content(self):
        page = SitePage.objects.create(
            path='/', navigation_title='Home', browser_title='English title',
            meta_description='English metadata', hero_title='English hero', is_published=True,
        )
        SitePageTranslation.objects.create(
            page=page, language_code='ha', navigation_title='Gida', browser_title='Otal a Abuja',
            meta_description='Bayani a Hausa', hero_title='Barka da zuwa',
            hero_summary='Ku huta lafiya.', is_published=True,
        )
        place = LocalGuidePlace.objects.create(
            name='City Park', category='landmark', summary='English summary', is_published=True,
        )
        LocalGuidePlaceTranslation.objects.create(
            place=place, language_code='ha', name='Filin Birni', summary='Bayani na Hausa',
            is_published=True,
        )
        home = self.client.get(reverse('frontend:public-home'), {'lang': 'ha'})
        self.assertContains(home, '<html lang="ha">')
        self.assertContains(home, 'Barka da zuwa')
        guide = self.client.get(reverse('frontend:public-guide'))
        self.assertContains(guide, 'Filin Birni')
        self.assertNotContains(guide, 'English summary')

    def test_guide_is_in_sitemap_and_search(self):
        sitemap = self.client.get(reverse('frontend:public-sitemap'))
        self.assertContains(sitemap, '/local-guide/')
        search = self.client.get(reverse('frontend:public-search'), {'q': 'Abuja'})
        self.assertContains(search, '/local-guide/')
