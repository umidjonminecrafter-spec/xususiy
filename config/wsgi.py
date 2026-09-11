import os
import sys
import threading
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Asosiy Django ilovasi ishga tushadi
application = get_wsgi_application()


def start_scheduler_safely():
    """
    Dars eslatmalari va kunlik hisobotlar schedulerini xavfsiz ishga tushirish.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from academics.tasks import check_and_send_lesson_reminders, send_daily_telegram_reports

        scheduler = BackgroundScheduler()
        # Har 1 daqiqada darslarni tekshirib eslatma yuboradi
        scheduler.add_job(check_and_send_lesson_reminders, 'interval', minutes=1, id='lesson_reminders', replace_existing=True)

        # Har kuni soat 9:00 da (Toshkent vaqti bilan) kunlik hisobotlarni yuboradi
        try:
            scheduler.add_job(
                send_daily_telegram_reports,
                'cron',
                hour=9,
                minute=0,
                timezone='Asia/Tashkent',
                id='daily_reports',
                replace_existing=True
            )
        except Exception as es:
            print(f"[WARN] Kunlik hisobot schedulerini sozlashda xatolik: {str(es)}")

        scheduler.start()
        print("[OK] Telegram Bot scheduler-i fonda muvaffaqiyatli ishga tushdi!")
    except Exception as e:
        print(f"[WARN] Scheduler ishga tushishida ogohlantirish: {str(e)}")


# Faqat asosiy ishchi jarayonida (yoki runserver da) scheduler ishga tushadi
if "runserver" in sys.argv or os.environ.get('ENABLE_SCHEDULER', 'true').lower() == 'true':
    # Gunicorn workerlarida takrorlanmasligi va bloklamasligi uchun alohida daemonic threadda yoqamiz
    threading.Thread(target=start_scheduler_safely, daemon=True).start()