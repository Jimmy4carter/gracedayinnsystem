from html.parser import HTMLParser

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import LocalGuidePlace


class SemanticAuditParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.labels = set()
        self.controls = []
        self.images_without_alt = []
        self.main_count = 0
        self.h1_count = 0
        self.html_language = ''
        self.viewport = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get('id'):
            self.ids.append(values['id'])
        if tag == 'label' and values.get('for'):
            self.labels.add(values['for'])
        if tag in {'input', 'select', 'textarea'} and values.get('type') != 'hidden':
            self.controls.append(values)
        if tag == 'img' and 'alt' not in values:
            self.images_without_alt.append(values.get('src', 'unknown'))
        if tag == 'main':
            self.main_count += 1
        if tag == 'h1':
            self.h1_count += 1
        if tag == 'html':
            self.html_language = values.get('lang', '')
        if tag == 'meta' and values.get('name') == 'viewport':
            self.viewport = True


class PublicQualityGateTests(TestCase):
    def _parse(self, response):
        parser = SemanticAuditParser()
        parser.feed(response.content.decode())
        return parser

    def test_critical_public_pages_have_semantic_mobile_basics(self):
        for route in ('frontend:public-home', 'frontend:public-rooms', 'frontend:public-guide',
                      'frontend:public-contact', 'frontend:public-faq', 'frontend:public-policies'):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                parser = self._parse(response)
                self.assertTrue(parser.html_language)
                self.assertTrue(parser.viewport)
                self.assertEqual(parser.main_count, 1)
                self.assertGreaterEqual(parser.h1_count, 1)
                self.assertEqual(parser.images_without_alt, [])
                self.assertEqual(len(parser.ids), len(set(parser.ids)), 'Duplicate HTML ids found.')

    def test_local_guide_form_controls_have_accessible_names(self):
        response = self.client.get(reverse('frontend:public-guide'))
        parser = self._parse(response)
        for control in parser.controls:
            with self.subTest(control=control.get('id')):
                self.assertTrue(
                    control.get('aria-label') or control.get('id') in parser.labels,
                    f"Control {control.get('name')} has no associated label.",
                )

    def test_local_guide_query_and_document_size_budgets(self):
        LocalGuidePlace.objects.bulk_create([
            LocalGuidePlace(
                name=f'Place {index}', category='landmark', summary='Useful destination.',
                is_published=True, display_order=index,
            ) for index in range(12)
        ])
        # Warm session and feature-flag lookups before measuring the page itself.
        self.client.get(reverse('frontend:public-guide'))
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse('frontend:public-guide'))
        self.assertLessEqual(len(queries), 12, f'Guide query budget exceeded: {len(queries)}')
        self.assertLess(len(response.content), 300_000, 'Guide HTML exceeds the 300 KB budget.')
