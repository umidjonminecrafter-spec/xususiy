import requests
from django.core.management.base import BaseCommand
from organizations.models import TelegramNotificationSetting
from academics.telegram_bot import REPORT_BOT_TOKEN, STUDENT_BOT_TOKEN, STAFF_BOT_TOKEN


class Command(BaseCommand):
    help = "Server va Telegram o'rtasida Webhook'larni o'rnatish yoki o'chirish"

    def add_arguments(self, parser):
        parser.add_argument('--domain', type=str, default='etirof.pythonanywhere.com', help='Server domeningiz (masalan: musojon1995.pythonanywhere.com)')
        parser.add_argument('--delete', action='store_true', help='Barcha webhooklarni o\'chirish (polling rejimiga o\'tish uchun)')
        parser.add_argument('--report-token', type=str, default=None, help='Hisobot bot tokeni')
        parser.add_argument('--student-token', type=str, default=None, help='Talaba bot tokeni')
        parser.add_argument('--staff-token', type=str, default=None, help='Xodimlar bot tokeni')

    def handle(self, *args, **options):
        domain = options['domain'].strip().replace('https://', '').replace('http://', '').strip('/')
        delete_mode = options.get('delete', False)

        report_token = options.get('report_token')
        student_token = options.get('student_token')
        staff_token = options.get('staff_token')

        settings = TelegramNotificationSetting.objects.all()

        raw_bots = []
        for s in settings:
            if s.bot_token:
                raw_bots.append(('reports', s.bot_token.strip()))
            if s.verification_bot_token:
                raw_bots.append(('verification', s.verification_bot_token.strip()))
            if s.student_bot_token:
                raw_bots.append(('student', s.student_bot_token.strip()))
            if s.parent_bot_token:
                raw_bots.append(('parent', s.parent_bot_token.strip()))
            if s.staff_bot_token:
                raw_bots.append(('staff', s.staff_bot_token.strip()))
            if s.support_bot_token:
                raw_bots.append(('support', s.support_bot_token.strip()))

        # Standart fallbacklar
        if report_token:
            raw_bots.append(('reports', report_token))
        elif not any(b[0] == 'reports' for b in raw_bots):
            raw_bots.append(('reports', REPORT_BOT_TOKEN))

        if student_token:
            raw_bots.append(('student', student_token))
        elif not any(b[0] == 'student' for b in raw_bots):
            raw_bots.append(('student', STUDENT_BOT_TOKEN))

        if staff_token:
            raw_bots.append(('staff', staff_token))
        elif not any(b[0] == 'staff' for b in raw_bots):
            raw_bots.append(('staff', STAFF_BOT_TOKEN))

        # Unikal botlar
        active_bots = []
        seen_tokens = set()
        for b_type, t_val in raw_bots:
            if t_val and (b_type, t_val) not in seen_tokens:
                active_bots.append((b_type, t_val))
                seen_tokens.add((b_type, t_val))

        for bot_type, token in active_bots:
            masked_token = token[:10] + "..." + token[-4:] if len(token) > 15 else token

            if delete_mode:
                try:
                    res = requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=6)
                    if res.status_code == 200 and res.json().get('ok'):
                        self.stdout.write(self.style.SUCCESS(f"🗑️ Webhook o'chirildi ({bot_type} | {masked_token})"))
                    else:
                        self.stdout.write(self.style.ERROR(f"❌ Webhook o'chirishda xato ({bot_type} | {masked_token}): {res.text}"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"❌ Xatolik ({bot_type} | {masked_token}): {str(e)}"))
            else:
                webhook_url = f"https://{domain}/api/telegram/webhook/{bot_type}/{token}/"
                try:
                    res = requests.get(f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}", timeout=6)
                    if res.status_code == 200 and res.json().get('ok'):
                        self.stdout.write(self.style.SUCCESS(f"✅ Webhook o'rnatildi ({bot_type} | {masked_token}): {webhook_url}"))
                    else:
                        self.stdout.write(self.style.ERROR(f"❌ Webhook xatosi ({bot_type} | {masked_token}): {res.text}"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"❌ Xatolik ({bot_type} | {masked_token}): {str(e)}"))
