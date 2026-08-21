from django.db import OperationalError, ProgrammingError

from .models import OperationalSetting, SitePage
from .feature_flags import flag_enabled


def public_site_page(request):
    if request.path.startswith('/portal/') or request.path.startswith('/api/'):
        return {}
    pages = SitePage.objects.filter(path=request.path)
    if not (request.user.is_authenticated and request.user.is_staff and request.GET.get('preview') == '1'):
        pages = pages.filter(is_published=True)
    try:
        page = pages.first()
    except (OperationalError, ProgrammingError):
        page = None
    supported_languages = {'en': 'English', 'fr': 'FranÃ§ais', 'ha': 'Hausa'}
    requested_language = (request.GET.get('lang') or request.session.get('public_language') or 'en').lower()
    if requested_language not in supported_languages:
        requested_language = 'en'
    if request.GET.get('lang') in supported_languages:
        request.session['public_language'] = requested_language
    translation = None
    if page and requested_language != 'en':
        translation = page.translations.filter(
            language_code=requested_language, is_published=True,
        ).first()
    from django.conf import settings
    whatsapp_number = getattr(settings, 'WHATSAPP_NUMBER', '')
    whatsapp_message = getattr(settings, 'WHATSAPP_DEFAULT_MESSAGE', '')
    try:
        whatsapp = OperationalSetting.objects.filter(key='whatsapp-contact').first()
        if whatsapp and isinstance(whatsapp.value, dict):
            whatsapp_number = whatsapp.value.get('number') or whatsapp_number
            whatsapp_message = whatsapp.value.get('message') or whatsapp_message
    except (OperationalError, ProgrammingError):
        pass
    whatsapp_number = ''.join(character for character in str(whatsapp_number) if character.isdigit())
    from urllib.parse import quote
    return {
        'site_page': page,
        'site_page_translation': translation,
        'public_language': requested_language,
        'public_languages': supported_languages,
        'whatsapp_url': (
            f'https://wa.me/{whatsapp_number}?text={quote(whatsapp_message)}'
            if whatsapp_number else ''
        ),
        'whatsapp_number': whatsapp_number,
        'public_features': {
            'booking': flag_enabled('public-booking', user=request.user, default=True),
        },
    }
