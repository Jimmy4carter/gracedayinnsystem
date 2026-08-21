from .models import AnalyticsEvent


ALLOWED_METADATA_KEYS = {
    'room_id', 'room_type_id', 'quote_reference', 'reservation_number',
    'result_count', 'query_length', 'error_code', 'source', 'promotion_code',
}


def record_event(request, event_name, **metadata):
    if not request.session.session_key:
        request.session.create()
    cleaned = {key: value for key, value in metadata.items() if key in ALLOWED_METADATA_KEYS}
    return AnalyticsEvent.objects.create(
        event_name=event_name,
        path=request.path[:255],
        session_key=request.session.session_key or '',
        user=request.user if request.user.is_authenticated else None,
        metadata=cleaned,
    )
