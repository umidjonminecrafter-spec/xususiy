"""
Common utility functions for SmartTalim backend.
Centralizes phone normalization, payment method mapping, date parsing, and currency formatting.
"""

from decimal import Decimal
from django.utils import timezone
import datetime


def normalize_uz_phone(phone):
    """
    O'zbekiston telefon raqamlarini yagona +998XXXXXXXXX formatga keltiradi.
    Agar noto'g'ri bo'lsa, None qaytaradi.
    """
    if not phone:
        return None
    cleaned = ''.join(c for c in str(phone) if c.isdigit())
    if len(cleaned) == 9:
        cleaned = '998' + cleaned
    elif len(cleaned) == 12 and cleaned.startswith('998'):
        pass
    else:
        # Invalid format
        if not cleaned:
            return None
        return '+' + cleaned
    return '+' + cleaned


def normalize_payment_method(method):
    """
    Kiritilgan har qanday to'lov usulini 3 xil asosiy turga (naqd, plastik, terminal/bank)
    standartlashtirib beruvchi yagona funksiya.
    """
    if not method:
        return 'naqd'
    m = str(method).lower().strip().replace('_', ' ').replace('-', ' ')
    if any(k in m for k in ('naqd', 'cash', 'pul')):
        return 'naqd'
    elif any(k in m for k in ('plastik', 'card', 'terminal', 'karta', 'humo', 'uzcard', 'click', 'payme', 'uzum')):
        return 'plastik'
    elif any(k in m for k in ('bank', 'transfer', 'hisob', 'otkazma', "o'tkazma")):
        return 'terminal'
    return 'naqd'


def parse_flexible_date(date_val, default=None):
    """
    DD/MM/YYYY, DD.MM.YYYY, DD-MM-YYYY yoki YYYY-MM-DD formatidagi sanalarni
    standart YYYY-MM-DD formatga o'tkazadi yoki date obyektini qaytaradi.
    """
    if not date_val:
        return default if default is not None else timezone.now().date()
    if isinstance(date_val, (datetime.date, datetime.datetime)):
        return date_val if isinstance(date_val, datetime.date) else date_val.date()
    
    d_str = str(date_val).strip()
    for sep in ('/', '.', '-'):
        if sep in d_str:
            parts = d_str.split(sep)
            if len(parts) == 3 and len(parts[0]) <= 2 and len(parts[2]) == 4:
                return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
    return d_str


def format_money(amount):
    """
    Summani '150 000 UZS' chiroyli formatda chiqaradi.
    """
    try:
        dec = Decimal(str(amount))
        return f"{int(dec):,} UZS".replace(",", " ")
    except (ValueError, TypeError):
        return f"{amount} UZS"
