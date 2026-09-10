import threading
import time
from django.utils import timezone
from django.db import connection


class BackupScheduler(threading.Thread):
    """
    Background scheduler that periodically checks BackupSetting and runs backups when due.
    """

    def __init__(self):
        super().__init__()
        self.daemon = True
        self.name = "SmartTalimBackupScheduler"

    def run(self):
        # Server to‘liq ishga tushib olishi uchun 15 soniya kutamiz
        time.sleep(15)
        print("smartTalim Backup Scheduler started.")

        while True:
            try:
                self.check_and_run_backups()
            except Exception as e:
                print(f"Backup scheduler running error: {str(e)}")
            # Har 5 daqiqada tekshiradi
            time.sleep(300)

    def check_and_run_backups(self):
        from organizations.models import BackupSetting
        from organizations.backup import run_backup_for_setting

        # PostgreSQL/Neon ulanishini thread-safe (oqimlar uchun xavfsiz) yangilash
        connection.close()

        active_settings = BackupSetting.objects.filter(is_active=True)
        now = timezone.now()

        for setting in active_settings:
            run_needed = False
            if not setting.last_run_at:
                run_needed = True
            else:
                elapsed = now - setting.last_run_at
                # Vaqt oralig‘i kelganini tekshirish
                if elapsed.total_seconds() >= (setting.interval_hours * 3600):
                    run_needed = True

            if run_needed:
                print(f"Running scheduled backup for organization: {setting.organization.name}")
                # Har bir so‘rovdan oldin ulanishni tozalash (PostgreSQL muammosini oldini oladi)
                connection.close()
                success, msg = run_backup_for_setting(setting)
                print(f"Scheduled backup status: {'SUCCESS' if success else 'FAILED'} - {msg}")