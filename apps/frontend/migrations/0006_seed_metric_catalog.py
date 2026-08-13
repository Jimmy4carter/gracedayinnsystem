from django.db import migrations


METRICS = [
    ('occupancy', 'Occupancy', 'Occupied sellable rooms divided by available sellable rooms.', 'occupied_rooms / available_rooms * 100', 'percent', ['reservations.Reservation', 'rooms.Room']),
    ('adr', 'Average Daily Rate', 'Recognized accommodation revenue divided by occupied rooms.', 'room_revenue / occupied_rooms', 'currency', ['billing.FolioEntry', 'reservations.Reservation']),
    ('revpar', 'Revenue per Available Room', 'Recognized accommodation revenue divided by available rooms.', 'room_revenue / available_rooms', 'currency', ['billing.FolioEntry', 'rooms.Room']),
    ('total_revenue', 'Total Revenue', 'Accommodation plus service debits less refunds posted on the business date.', 'accommodation + service - refunds', 'currency', ['billing.FolioEntry']),
    ('receivables', 'Receivables', 'Sum of positive balances on open guest folios.', 'sum(max(folio.balance, 0))', 'currency', ['billing.Folio', 'billing.FolioEntry']),
    ('cash_variance', 'Cash Variance', 'Sum of closed cashier shift counted-minus-expected variances.', 'sum(cashier_shift.variance)', 'currency', ['payments.CashierShift']),
]


def seed_metrics(apps, schema_editor):
    MetricDefinition = apps.get_model('frontend', 'MetricDefinition')
    for key, name, description, formula, unit, source_models in METRICS:
        MetricDefinition.objects.update_or_create(
            key=key,
            defaults={
                'name': name, 'description': description, 'formula': formula,
                'unit': unit, 'source_models': source_models, 'is_active': True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [('frontend', '0005_add_management_intelligence')]
    operations = [migrations.RunPython(seed_metrics, migrations.RunPython.noop)]
