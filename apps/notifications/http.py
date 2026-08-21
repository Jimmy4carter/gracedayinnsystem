import urllib.request
from urllib.parse import urlparse

from django.core.exceptions import SuspiciousOperation


BREVO_API_HOST = 'api.brevo.com'


def _validate_brevo_url(url):
    parsed = urlparse(url)
    if (
        parsed.scheme != 'https'
        or parsed.hostname != BREVO_API_HOST
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise SuspiciousOperation('Brevo requests must use the approved HTTPS API host.')


class _BrevoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_brevo_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_brevo_request(request, *, timeout=15):
    _validate_brevo_url(request.full_url)
    opener = urllib.request.build_opener(_BrevoRedirectHandler())
    # Bandit B310: the initial URL and every redirect are restricted above to Brevo HTTPS.
    return opener.open(request, timeout=timeout)  # nosec B310
