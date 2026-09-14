from django.core.management.base import BaseCommand
from organizations.models import Branch, Organization
from accounts.models import WeeklyLessonHour


class Command(BaseCommand):
    help = "Har bir filial uchun 1 dan 50 gacha haftalik dars soatlarini avtomatik yaratish"

    def handle(self, *args, **options):
        branches = Branch.objects.all().select_related('organization')
        if not branches.exists():
            org = Organization.objects.first()
            if not org:
                org = Organization.objects.create(name="Asosiy Tashkilot")
            branches = [Branch.objects.create(name="Asosiy Filial", organization=org)]

        total_created = 0
        for branch in branches:
            self.stdout.write(f"Filial: {branch.name} (Org: {branch.organization.name})...")
            for h in range(1, 51):
                hour_val = float(h)
                obj, created = WeeklyLessonHour.objects.get_or_create(
                    organization=branch.organization,
                    branch=branch,
                    hours=hour_val,
                    defaults={
                        'name': f"{h} soat"
                    }
                )
                if created:
                    total_created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Muvaffaqiyatli yakunlandi! Jami {total_created} ta yangi dars soati qo'shildi. "
            f"(Bazada jami: {WeeklyLessonHour.objects.count()} ta)"
        ))
