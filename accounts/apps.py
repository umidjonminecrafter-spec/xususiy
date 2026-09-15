from django.apps import AppConfig
import sys


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        if 'test' in sys.argv:
            return

        try:
            from django.db import connection
            with connection.cursor() as cursor:
                vendor = connection.vendor
                if vendor == 'sqlite':
                    cursor.execute("PRAGMA table_info(accounts_user);")
                    columns = [col[1] for col in cursor.fetchall()]
                    if columns:
                        if 'hourly_rate' not in columns:
                            cursor.execute("ALTER TABLE accounts_user ADD COLUMN hourly_rate decimal DEFAULT 0.0;")
                        if 'weekly_hours' not in columns:
                            cursor.execute("ALTER TABLE accounts_user ADD COLUMN weekly_hours decimal DEFAULT 0.0;")
                        if 'salary_type' not in columns:
                            cursor.execute("ALTER TABLE accounts_user ADD COLUMN salary_type varchar(20) DEFAULT 'percentage';")
                        if 'fixed_salary' not in columns:
                            cursor.execute("ALTER TABLE accounts_user ADD COLUMN fixed_salary decimal DEFAULT 0.0;")
                        if 'salary_percentage_id' not in columns:
                            cursor.execute("ALTER TABLE accounts_user ADD COLUMN salary_percentage_id bigint NULL;")
                        if 'telegram_language' not in columns:
                            cursor.execute("ALTER TABLE accounts_user ADD COLUMN telegram_language varchar(5) DEFAULT 'uz';")
                elif vendor in ('mysql', 'postgresql'):
                    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='accounts_user';")
                    columns = [row[0] for row in cursor.fetchall()]
                    if columns:
                        if 'hourly_rate' not in columns:
                            cursor.execute("ALTER TABLE accounts_user ADD COLUMN hourly_rate DECIMAL(12,2) DEFAULT 0.0;")
                        if 'weekly_hours' not in columns:
                            cursor.execute("ALTER TABLE accounts_user ADD COLUMN weekly_hours DECIMAL(8,2) DEFAULT 0.0;")
                        if 'salary_type' not in columns:
                            cursor.execute("ALTER TABLE accounts_user ADD COLUMN salary_type VARCHAR(20) DEFAULT 'percentage';")
                        if 'fixed_salary' not in columns:
                            cursor.execute("ALTER TABLE accounts_user ADD COLUMN fixed_salary DECIMAL(12,2) DEFAULT 0.0;")
                        if 'salary_percentage_id' not in columns:
                            cursor.execute("ALTER TABLE accounts_user ADD COLUMN salary_percentage_id BIGINT NULL;")
                        if 'telegram_language' not in columns:
                            cursor.execute("ALTER TABLE accounts_user ADD COLUMN telegram_language VARCHAR(5) DEFAULT 'uz';")
        except Exception:
            pass
