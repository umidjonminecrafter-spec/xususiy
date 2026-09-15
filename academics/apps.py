from django.apps import AppConfig
from django.db.models.signals import post_migrate


def auto_heal_academics_schema(sender, **kwargs):
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            vendor = connection.vendor
            if vendor == 'sqlite':
                cursor.execute("PRAGMA table_info(academics_group);")
                columns = [col[1] for col in cursor.fetchall()]
                if columns:
                    if 'language' not in columns:
                        cursor.execute("ALTER TABLE academics_group ADD COLUMN language varchar(20) DEFAULT 'uz';")
                    if 'capacity' not in columns:
                        cursor.execute("ALTER TABLE academics_group ADD COLUMN capacity integer NULL;")
                    if 'grade_level' not in columns:
                        cursor.execute("ALTER TABLE academics_group ADD COLUMN grade_level integer NULL;")
                    if 'section' not in columns:
                        cursor.execute("ALTER TABLE academics_group ADD COLUMN section varchar(10) NULL;")
            elif vendor in ('mysql', 'postgresql'):
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='academics_group';")
                columns = [row[0] for row in cursor.fetchall()]
                if columns:
                    if 'language' not in columns:
                        cursor.execute("ALTER TABLE academics_group ADD COLUMN language VARCHAR(20) DEFAULT 'uz';")
                    if 'capacity' not in columns:
                        cursor.execute("ALTER TABLE academics_group ADD COLUMN capacity INT NULL;")
                    if 'grade_level' not in columns:
                        cursor.execute("ALTER TABLE academics_group ADD COLUMN grade_level INT NULL;")
                    if 'section' not in columns:
                        cursor.execute("ALTER TABLE academics_group ADD COLUMN section VARCHAR(10) NULL;")
    except Exception:
        pass


class AcademicsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'academics'

    def ready(self):
        post_migrate.connect(auto_heal_academics_schema, sender=self)
