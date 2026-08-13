import urllib.request
from unittest.mock import Mock, patch

from django.core.exceptions import SuspiciousOperation
from django.test import SimpleTestCase

from .http import _BrevoRedirectHandler, open_brevo_request


class BrevoHTTPBoundaryTests(SimpleTestCase):
    def test_only_approved_https_api_host_is_opened(self):
        request = urllib.request.Request('https://api.brevo.com/v3/smtp/email')
        response = Mock()
        opener = Mock()
        opener.open.return_value = response
        with patch('apps.notifications.http.urllib.request.build_opener', return_value=opener):
            self.assertIs(open_brevo_request(request), response)
        opener.open.assert_called_once_with(request, timeout=15)

    def test_file_http_credentials_and_lookalike_hosts_are_rejected(self):
        for url in (
            'file:///etc/passwd',
            'http://api.brevo.com/v3/contacts',
            'https://key@api.brevo.com/v3/contacts',
            'https://api.brevo.com.evil.example/v3/contacts',
        ):
            with self.subTest(url=url), self.assertRaises(SuspiciousOperation):
                open_brevo_request(urllib.request.Request(url))

    def test_redirect_handler_rejects_off_host_redirect(self):
        handler = _BrevoRedirectHandler()
        request = urllib.request.Request('https://api.brevo.com/v3/contacts')
        with self.assertRaises(SuspiciousOperation):
            handler.redirect_request(
                request, Mock(), 302, 'Found', {}, 'https://evil.example/collect'
            )
