import os
import sys
import datetime
from decimal import Decimal

# Django settings sozlash
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.contrib.auth import get_user_model
from organizations.models import (
    Organization, Branch, Tariff, Subscription, ReceiptSetting, 
    ExamSetting
)
from academics.models import (
    Course, Room, Student, Group, StudentGroup, GroupTeacher, 
    Attendance, LessonSchedule
)
from finance.models import (
    ExpenseCategory, ExpenseSubcategory, Cashbox, Payment, Expense, 
    StaffSalaryPercent, FinanceSetting, CashTransaction
)
from crm.models import Pipeline, Source, LostReason, Section, Lead
from tasks.models import Board, Column, Item
from support.models import FAQCategory, FAQItem

User = get_user_model()

print("=" * 60)
print("SmartTalim ma'lumotlarini boshlang'ich sozlash (Seeding)...")
print("=" * 60)

# 1. Standart Tariflar
tariffs_data = [
    {"name": "Basic", "price": Decimal("49.00"), "months": 1, "student_limit": 100, "features": {"students_limit": 100, "branches_limit": 1}},
    {"name": "Premium", "price": Decimal("99.00"), "months": 1, "student_limit": 500, "features": {"students_limit": 500, "branches_limit": 3}},
    {"name": "Enterprise", "price": Decimal("249.00"), "months": 1, "student_limit": 5000, "features": {"students_limit": 5000, "branches_limit": 10}},
]
created_tariffs = {}
for t_data in tariffs_data:
    t, _ = Tariff.objects.get_or_create(name=t_data["name"], defaults=t_data)
    created_tariffs[t.name] = t
    print(f"Tarif: {t.name}")

# 2. Superuser (admin / salom12345)
if not User.objects.filter(username="admin").exists():
    superuser = User.objects.create_superuser(
        username="admin",
        password="salom12345",
        email="admin@smarttalim.uz",
        first_name="Bosh",
        last_name="Administrator",
        phone="+998901234567",
        role="owner",
        organization=None
    )
    print(f"Superuser yaratildi: admin / salom12345")
else:
    su = User.objects.get(username="admin")
    su.set_password("salom12345")
    su.is_superuser = True
    su.is_staff = True
    su.save()
    print("Superuser 'admin' paroli 'salom12345' ga yangilandi.")

# 3. Tashkilot (Smart Academy)
org, org_created = Organization.objects.get_or_create(
    name="Smart Academy",
    defaults={
        "subdomain": "smartacademy",
        "phone": "+998774578407",
        "address": "Toshkent sh., Chilonzor tumani, Bunyodkor shoh ko'chasi 15-uy"
    }
)
print(f"Tashkilot: {org.name} ({org.phone})")

# 4. Tashkilot Egasi / Admini (+998774578407 / admin12345)
if not User.objects.filter(username="+998774578407").exists():
    org_admin = User.objects.create_user(
        username="+998774578407",
        password="admin12345",
        phone="+998774578407",
        first_name="Tashkilot",
        last_name="Rahbari",
        email="info@smartacademy.uz",
        role="owner",
        organization=org,
        is_staff=True,
        is_active=True
    )
    print(f"Tashkilot admini yaratildi: +998774578407 / admin12345")
else:
    org_admin = User.objects.get(username="+998774578407")
    org_admin.set_password("admin12345")
    org_admin.organization = org
    org_admin.save()
    print("Tashkilot admini paroli yangilandi.")

# 5. Tashkilot obunasi
Subscription.objects.get_or_create(
    organization=org,
    defaults={
        "tariff": created_tariffs.get("Premium"),
        "start_date": datetime.date.today(),
        "end_date": datetime.date.today() + datetime.timedelta(days=365),
        "is_active": True,
        "balance": Decimal("1000000.00")
    }
)

# 6. Filial
branch, _ = Branch.objects.get_or_create(
    organization=org,
    name="Chilonzor filiali",
    defaults={
        "address": "Toshkent sh., Chilonzor tumani, 9-mavze",
        "phone": "+998774578407"
    }
)
org_admin.branch = branch
org_admin.branches.add(branch)
org_admin.save()

# 7. Xona
room, _ = Room.objects.get_or_create(
    organization=org,
    branch=branch,
    name="101-xona (Cambridge)",
    defaults={
        "capacity": 20,
        "comment": "Interaktiv doska va proyektor bilan jihozlangan"
    }
)

# 8. Kurs
course, _ = Course.objects.get_or_create(
    organization=org,
    branch=branch,
    name="General English (Pre-Intermediate)",
    defaults={
        "description": "Ingliz tilini noldan o'rganuvchilar uchun 3 oylik intensiv dastur",
        "price": Decimal("600000.00"),
        "duration_weeks": 12,
        "code": "ENG-B1",
        "lesson_time": "90 daqiqa"
    }
)

# 9. O'qituvchi foiz stavkasi va O'qituvchi
salary_percent, _ = StaffSalaryPercent.objects.get_or_create(
    organization=org,
    branch=branch,
    name="Katta o'qituvchi stavkasi",
    defaults={
        "percent": Decimal("40.00"),
        "comment": "Har bir talaba to'lovidan 40% foiz"
    }
)

if not User.objects.filter(username="+998901112233_1").exists():
    teacher = User.objects.create_user(
        username="+998901112233_1",
        phone="+998901112233",
        password="teacher12345",
        first_name="Alisher",
        last_name="Qodirov",
        email="alisher.teacher@smartacademy.uz",
        role="teacher",
        position="Bosh ingliz tili o'qituvchisi",
        organization=org,
        branch=branch,
        salary_percentage=salary_percent,
        is_active=True
    )
    teacher.branches.add(branch)
else:
    teacher = User.objects.get(username="+998901112233_1")

# 10. Guruh
group, _ = Group.objects.get_or_create(
    organization=org,
    branch=branch,
    name="ENG-B1 (Guruh 01)",
    defaults={
        "course": course,
        "room": room,
        "teacher": teacher,
        "status": "active",
        "education_type": "offline",
        "days": ["Dushanba", "Chorshanba", "Juma"],
        "start_time": datetime.time(14, 0),
        "end_time": datetime.time(15, 30),
        "start_date": datetime.date(2026, 9, 1),
        "end_date": datetime.date(2026, 11, 30)
    }
)

# 11. O'quvchi (Student)
student, _ = Student.objects.get_or_create(
    organization=org,
    branch=branch,
    phone="+998912345678",
    defaults={
        "first_name": "Azizbek",
        "last_name": "Sobirov",
        "email": "azizbek@example.com",
        "balance": Decimal("600000.00"),
        "birth_date": datetime.date(2006, 5, 20),
        "address": "Toshkent sh., Yunusobod 4-mavze"
    }
)

StudentGroup.objects.get_or_create(organization=org, branch=branch, student=student, group=group, defaults={"price": course.price})
GroupTeacher.objects.get_or_create(organization=org, branch=branch, group=group, teacher=teacher)

# 12. Dars jadvali va Davomat
LessonSchedule.objects.get_or_create(
    organization=org,
    branch=branch,
    group=group,
    day_type="odd",
    defaults={
        "room_name": "101-xona (Cambridge)",
        "teacher": teacher,
        "start_time": datetime.time(14, 0),
        "end_time": datetime.time(15, 30)
    }
)
Attendance.objects.get_or_create(
    organization=org,
    branch=branch,
    group=group,
    student=student,
    date=datetime.date.today(),
    defaults={
        "status": "present",
        "grade": 5,
        "reason": "Darsda faol qatnashdi"
    }
)

# 13. Kassa va To'lov
cashbox, _ = Cashbox.objects.get_or_create(
    organization=org,
    branch=branch,
    name="Asosiy Kassa (Naqd / Karta)",
    defaults={"balance": Decimal("0.00")}
)
CashTransaction.objects.get_or_create(
    organization=org,
    cashbox=cashbox,
    transaction_type="kirim",
    payment_method="naqd",
    defaults={
        "amount": Decimal("1000000.00"),
        "date": datetime.date.today(),
        "category_name": "Boshlang'ich kassa kapitali",
        "comment": "Kassa ochilishidagi dastlabki mablag'"
    }
)
Payment.objects.get_or_create(
    organization=org,
    branch=branch,
    student=student,
    date=datetime.date.today(),
    defaults={
        "amount": Decimal("600000.00"),
        "cashbox": cashbox,
        "payment_method": "Naqd",
        "employee": org_admin,
        "comment": "1-oylik kurs to'lovi"
    }
)

# 14. Xarajatlar
exp_cat, _ = ExpenseCategory.objects.get_or_create(organization=org, branch=branch, name="Kommunal to'lovlar")
exp_subcat, _ = ExpenseSubcategory.objects.get_or_create(organization=org, branch=branch, category=exp_cat, name="Internet va Wi-Fi")
Expense.objects.get_or_create(
    organization=org,
    branch=branch,
    category=exp_cat,
    subcategory=exp_subcat,
    date=datetime.date.today(),
    defaults={
        "amount": Decimal("150000.00"),
        "cashbox": cashbox,
        "description": "Optik tolali internet xizmati uchun oylik to'lov"
    }
)

# 15. CRM
p_new, _ = Pipeline.objects.get_or_create(organization=org, branch=branch, name="Yangi lidlar", defaults={"order": 1})
Pipeline.objects.get_or_create(organization=org, branch=branch, name="Sinov darsi", defaults={"order": 2})
Pipeline.objects.get_or_create(organization=org, branch=branch, name="Guruhga qabul qilindi", defaults={"order": 3})

crm_source, _ = Source.objects.get_or_create(organization=org, branch=branch, name="Instagram Reklama")
LostReason.objects.get_or_create(organization=org, branch=branch, reason="Dars vaqti to'g'ri kelmadi")
crm_section, _ = Section.objects.get_or_create(organization=org, branch=branch, name="Ingliz tili bo'limi", defaults={"pipeline": p_new})

Lead.objects.get_or_create(
    organization=org,
    branch=branch,
    phone="+998935556677",
    defaults={
        "name": "Jasur Nematov",
        "email": "jasur@example.com",
        "status": "open",
        "pipeline": p_new,
        "source": crm_source,
        "section": crm_section,
        "created_by": org_admin,
        "comment": "Instagram orqali murojaat qildi, sinov darsiga qiziqmoqda"
    }
)

# 16. Vazifalar
board, _ = Board.objects.get_or_create(
    organization=org,
    branch=branch,
    name="O'quv markazi vazifalari",
    defaults={"description": "Markazning kundalik boshqaruv va marketing vazifalari"}
)
col, _ = Column.objects.get_or_create(
    organization=org,
    branch=branch,
    board=board,
    name="Bajarilmoqda",
    defaults={"order": 1}
)
Item.objects.get_or_create(
    organization=org,
    branch=branch,
    board=board,
    column=col,
    title="Ochiq eshiklar kuni (Masterklass) o'tkazish",
    defaults={
        "description": "Yangi o'quvchilar uchun bepul sinov darsi va taqdimot tashkil qilish",
        "assigned_to": org_admin,
        "order": 1
    }
)

# 17. FAQ
faq_cat, _ = FAQCategory.objects.get_or_create(organization=org, branch=branch, name="Umumiy ma'lumotlar")
FAQItem.objects.get_or_create(
    organization=org,
    branch=branch,
    category=faq_cat,
    question="Darslar qayerda va qanday tartibda o'tiladi?",
    defaults={
        "answer": "Darslarimiz Chilonzor filialimizda haftasiga 3 marta, 90 daqiqadan tajribali o'qituvchilar tomonidan o'tiladi.",
        "keywords": ["dars", "manzil", "jadval"],
        "is_active": True
    }
)

# 18. Sozlamalar
ReceiptSetting.objects.get_or_create(organization=org, defaults={"hide_logo": False, "hide_balance": False})
ExamSetting.objects.get_or_create(organization=org, defaults={"include_active_students": True})
FinanceSetting.objects.get_or_create(organization=org, branch=branch, defaults={"is_bonus_enabled": True})

print("=" * 60)
print("Barcha ma'lumotlar muvaffaqiyatli tayyorlandi!")
print("=" * 60)
