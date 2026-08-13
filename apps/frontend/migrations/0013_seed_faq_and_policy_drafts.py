from django.db import migrations


FAQS = [
    ('booking', 'How do I make a direct booking?', 'Choose dates and guests on the website, review the itemized quote and policies, verify your email, and confirm the booking. You can also contact the hotel for assisted booking.', 10),
    ('booking', 'Can I change or cancel a booking?', 'Use the secure manage-booking link in your confirmation or contact the hotel. Eligibility, fees and refund terms depend on the policy version accepted with your booking.', 20),
    ('payment', 'Which payment methods are accepted?', 'The hotel records supported over-the-counter methods at reception. Online payment availability is shown during booking when enabled. Never send card or account credentials through chat or email.', 10),
    ('stay', 'How can I request an early arrival or late departure?', 'Add the request to your booking or contact the hotel. Requests depend on room availability and are confirmed only when the hotel accepts them.', 10),
    ('services', 'Can hotel services be charged to my room?', 'Eligible services can be posted to an active guest folio after staff verify the room and guest. Some items may require immediate payment.', 10),
    ('accessibility', 'How do I share an accessibility requirement?', 'Add the requirement as a special request or contact the hotel before arrival. The team will confirm what can be provided for your selected room and dates.', 10),
]


POLICIES = [
    ('privacy-notice', 'privacy', 'Privacy notice'),
    ('booking-terms', 'booking', 'Booking terms'),
    ('cancellation-policy', 'cancellation', 'Cancellation policy'),
    ('cookie-notice', 'cookies', 'Cookie notice'),
    ('accessibility-statement', 'accessibility', 'Accessibility statement'),
    ('house-rules', 'house_rules', 'House rules'),
]


def seed_content(apps, schema_editor):
    FAQItem = apps.get_model('frontend', 'FAQItem')
    PolicyDocument = apps.get_model('frontend', 'PolicyDocument')
    for category, question, answer, order in FAQS:
        FAQItem.objects.get_or_create(
            question=question,
            defaults={'category': category, 'answer': answer, 'display_order': order, 'is_published': True},
        )
    for slug, policy_type, title in POLICIES:
        PolicyDocument.objects.get_or_create(
            slug=slug,
            defaults={
                'policy_type': policy_type, 'title': title,
                'summary': 'Owner and qualified-adviser review is required before publication.',
                'body': 'DRAFT - Replace this controlled placeholder with approved policy text before approval and publication.',
                'version': 'draft-1', 'review_status': 'draft', 'is_published': False,
            },
        )


class Migration(migrations.Migration):
    dependencies = [('frontend', '0012_faqitem_policydocument')]
    operations = [migrations.RunPython(seed_content, migrations.RunPython.noop)]
