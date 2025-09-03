from django import template

register = template.Library()

@register.filter
def subtract(value, arg):
    """Subtract one number from another."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter  
def percentage_change(close, open_price):
    """Calculate percentage change between close and open."""
    try:
        close_val = float(close)
        open_val = float(open_price)
        if open_val == 0:
            return 0
        return ((close_val - open_val) / open_val) * 100
    except (ValueError, TypeError):
        return 0
