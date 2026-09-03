import os
import sys
import threading
import time
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Asosiy Django ilovasi ishga tushadi
application = get_wsgi_application()


def is_db_ready():
    try:
        from django.db import connection
        tables = connection.introspection.table_names()
        return 'accounts_user' in tables and 'organizations_telegramnotificationsetting' in tables
    except Exception:
        return False


# ================= 1. SUPERUSER YARATISH QISMI =================
def ensure_superuser():
    try:
        if not is_db_ready():
            return
        from django.contrib.auth import get_user_model
        from django.contrib.auth.hashers import make_password

        User = get_user_model()
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@example.com', 'admin12345')
            print("[OK] Superuser muvaffaqiyatli yaratildi!")
        else:
            User.objects.filter(username='admin').update(
                password=make_password('admin12345'),
                is_staff=True,
                is_superuser=True,
                is_active=True,
            )
            print("[OK] Superuser paroli va flaglari yangilandi.")
    except Exception as e:
        print(f"[XATO] Superuser yaratishda xatolik yuz berdi: {e}")


# ================= 2. BOT VA SCHEDULERNI GLOBAL FONDA ISHGA TUSHIRISH =================
def start_bot_and_scheduler():
    time.sleep(5)
    ensure_superuser()

    if not is_db_ready():
        return

    # A) Dars eslatmalari taymerini (Scheduler) ishga tushirish
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from academics.tasks import check_and_send_lesson_reminders

        scheduler = BackgroundScheduler()
        # Har 1 daqiqada darslarni tekshirib eslatma yuboradi
        scheduler.add_job(check_and_send_lesson_reminders, 'interval', minutes=1)

        # Har kuni soat 9:00 da (Toshkent vaqti bilan) kunlik hisobotlarni yuboradi
        try:
            from academics.tasks import send_daily_telegram_reports
            scheduler.add_job(
                send_daily_telegram_reports,
                'cron',
                hour=9,
                minute=0,
                timezone='Asia/Tashkent'
            )
            print("[OK] Kunlik Telegram hisobotlari jadvali qo'shildi!")
        except Exception as es:
            print(f"[XATO] Kunlik hisobot schedulerini sozlashda xatolik: {str(es)}")

        # Har 1 soatda 7 kundan buyon qabul qilinmagan murojaatlarni tekshiradi
        try:
            from academics.tasks import check_and_escalate_unresolved_appeals
            scheduler.add_job(
                check_and_escalate_unresolved_appeals,
                'interval',
                hours=1
            )
            print("[OK] Murojaatlar eskalatsiyasi jadvali qo'shildi!")
        except Exception as ea:
            print(f"[XATO] Murojaatlar eskalatsiyasi schedulerini sozlashda xatolik: {str(ea)}")

        scheduler.start()
        print("[OK] Telegram Bot scheduler-i muvaffaqiyatli yurib ketdi!")
    except Exception as e:
        print(f"[XATO] Scheduler ishga tushishda xatolik: {str(e)}")

    # B) Telegram botning o'zini (Eshitish rejimini) fonda global yoqish
    try:
        from django.core.management import call_command
        print("[BOT] Telegram bot global rejimda (polling) ishga tushmoqda...")
        call_command('run_telegram_bots')
    except Exception as e:
        print(f"[XATO] Botni global yoqishda xatolik: {e}")


# Faqat asosiy protsessda ishga tushishini ta'minlash (Render va lokal muhit takrorlanish xavfsizligi)
if "runserver" in sys.argv or not os.environ.get('RUN_MAIN') == 'true':
    threading.Thread(target=start_bot_and_scheduler, daemon=True).start()