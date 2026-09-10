import os
import sys
import threading
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Asosiy Django ilovasi ishga tushadi
application = get_wsgi_application()

# ================= 1. SUPERUSER YARATISH QISMI =================
try:
    from django.contrib.auth import get_user_model
    from django.contrib.auth.hashers import make_password

    User = get_user_model()

    if not User.objects.filter(username='admin').exists():
        # Yangi superuser yaratamiz
        User.objects.create_superuser('admin', 'admin@example.com', 'admin12345')
        print("[OK] Superuser muvaffaqiyatli yaratildi!")
    else:
        # update() ishlatamiz - signallar va validatsiyani chetlab o'tadi
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

        scheduler.start()
        print("[OK] Telegram Bot scheduler-i muvaffaqiyatli yurib ketdi!")
    except Exception as e:
        print(f"[XATO] Scheduler ishga tushishda xatolik: {str(e)}")

    # B) Telegram botning o'zini (Eshitish rejimini) fonda global yoqish
    try:
        # academics/bot.py ichidagi main funksiyani chaqiramiz
        from academics.bot import main as start_telegram_bot
        print("[BOT] Telegram bot global rejimda (polling) ishga tushmoqda...")
        start_telegram_bot()
    except Exception as e:
        print(f"[XATO] Botni global yoqishda xatolik: {e}")


# Faqat asosiy protsessda ishga tushishini ta'minlash (Render va lokal muhit takrorlanish xavfsizligi)
if "runserver" in sys.argv or not os.environ.get('RUN_MAIN') == 'true':
    # Tizim qotib qolmasligi uchun alohida fonda (Thread) parallel yoqamiz
    threading.Thread(target=start_bot_and_scheduler, daemon=True).start()