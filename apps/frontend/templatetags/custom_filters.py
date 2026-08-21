from django import template
from decimal import Decimal, InvalidOperation

register = template.Library()

@register.filter(name='currency_format')
def currency_format(value):
    """
    Formats a number as currency with 2 decimal places and commas.
    Example: 45000 -> 45,000.00
    """
    try:
        if value is None:
            return "0.00"
        value = Decimal(str(value))
        return "{:,.2f}".format(value)
    except (ValueError, TypeError, InvalidOperation):
        return value
