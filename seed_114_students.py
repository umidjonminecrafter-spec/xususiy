import os
import django
import random
from decimal import Decimal
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from organizations.models import Organization, Branch
from academics.models import Student, SchoolClass, ClassStudent, Group, StudentGroup, Course, Parent, StudentAddress

User = get_user_model()

def seed_students(target_count=114):
    org = Organization.objects.first()
    if not org:
        org = Organization.objects.create(name="Smart Academy")
    
    branch = Branch.objects.filter(organization=org).first()
    if not branch:
        branch = Branch.objects.create(name="Asosiy filial", organization=org)

    # 1. Ensure courses and groups
    course, _ = Course.objects.get_or_create(
        organization=org,
        branch=branch,
        name="Ingliz tili (General English)",
        defaults={
            "price": Decimal("600000.00"),
            "duration_weeks": 12,
            "color": "#4F46E5",
            "is_active": True
        }
    )
    group, _ = Group.objects.get_or_create(
        organization=org,
        branch=branch,
        name="English-01",
        defaults={"course": course, "status": "active"}
    )

    # 2. Ensure school classes (1-A dan 11-A gacha)
    classes = []
    sections = ['A', 'B', 'V']
    for grade in range(1, 12):
        for sec in sections:
            sc, _ = SchoolClass.objects.get_or_create(
                organization=org,
                branch=branch,
                grade_level=str(grade),
                section=sec,
                academic_year="2026-2027",
                defaults={"language": "uz"}
            )
            classes.append(sc)

    # 3. Uzbek names dataset
    first_names_male = [
        "Azizbek", "Sardor", "Jasur", "Javohir", "Bekzod", "Dilshod", "Bobur", "Shaxzod",
        "Otabek", "Farrux", "Shohruh", "Diyorbek", "Ulug'bek", "Mirjalol", "Muhammadali",
        "Islom", "Ibrohim", "Bilol", "Abdulloh", "Mustafo", "Habibullo", "Samandar",
        "Bunyod", "Doniyor", "Sanjar", "Akbar", "Rustam", "Asadbek", "Jahongir", "Shavkat"
    ]
    first_names_female = [
        "Madina", "Shahzoda", "Nigora", "Zarina", "Dildora", "Gulzoda", "Rayhona", "Fotima",
        "Zuhra", "Muslimaxon", "Mubina", "Dilnoza", "Sevara", "Mohira", "Gulsanam", "Kamola",
        "Sabina", "Zilola", "Malika", "Laylo", "Jasmina", "Ruxshona", "Munisa", "Charos",
        "Nozima", "Gulbahor", "Shaxnoza", "Diyora", "Feruza", "Ozoda"
    ]
    last_names = [
        "Sobirov", "Karimov", "Aliyev", "Tursunov", "Rahimov", "Abdullayev", "Xoliqov",
        "Qodirov", "Ergashev", "Saidov", "Rustamov", "Ismoilov", "Yoqubov", "Nazarov",
        "Shokirov", "Valiyev", "Mirzayev", "Yusupov", "Ahmedov", "Sultonov", "G'aniyev",
        "Xusanov", "Mamatov", "Norbekov", "Polvonov", "Qurbonov", "Umarov", "Hamdamov"
    ]

    current_count = Student.objects.filter(organization=org).count()
    needed = target_count - current_count
    print(f"Joriy o'quvchilar soni: {current_count}. Qo'shilishi kerak: {needed}")

    created_count = 0
    phone_prefix_list = ['90', '91', '93', '94', '95', '97', '98', '99', '88', '33', '77']

    for i in range(1, target_count + 1):
        if Student.objects.filter(organization=org).count() >= target_count:
            break

        is_female = (i % 2 == 0)
        if is_female:
            fname = random.choice(first_names_female)
            lname = random.choice(last_names) + "a"
        else:
            fname = random.choice(first_names_male)
            lname = random.choice(last_names)

        # Generate unique phone number
        while True:
            prefix = random.choice(phone_prefix_list)
            suffix = f"{random.randint(1000000, 9999999)}"
            phone = f"+998{prefix}{suffix}"
            if not Student.objects.filter(phone=phone).exists() and not User.objects.filter(username=phone).exists():
                break

        assigned_class = random.choice(classes)
        birth_year = 2026 - 6 - int(assigned_class.grade_level)
        birth_date = datetime.date(birth_year, random.randint(1, 12), random.randint(1, 28))

        student = Student.objects.create(
            organization=org,
            branch=branch,
            first_name=fname,
            last_name=lname,
            phone=phone,
            email=f"{fname.lower()}.{lname.lower()}{i}@example.com",
            birth_date=birth_date,
            school_class=assigned_class,
            balance=Decimal(str(random.choice([0, 0, 0, 50000, 100000, 200000, -50000]))),
            address=f"Toshkent shahri, {random.choice(['Chilonzor', 'Yunusobod', 'Mirzo Ulugbek', 'Yakkasaroy', 'Shayxontohur'])} tumani",
            is_archived=False
        )

        # User account
        if not User.objects.filter(username=phone).exists():
            User.objects.create_user(
                username=phone,
                password="password123",
                first_name=fname,
                last_name=lname,
                phone=phone,
                role='student',
                organization=org,
                branch=branch
            )

        # ClassStudent
        ClassStudent.objects.get_or_create(
            organization=org,
            branch=branch,
            student=student,
            school_class=assigned_class,
            defaults={"is_active": True}
        )

        # StudentGroup
        StudentGroup.objects.get_or_create(
            organization=org,
            branch=branch,
            student=student,
            group=group,
            defaults={"price": course.price}
        )

        # Parent
        parent_phone = f"+998{random.choice(phone_prefix_list)}{random.randint(1000000, 9999999)}"
        Parent.objects.create(
            organization=org,
            branch=branch,
            student=student,
            full_name=f"{lname} {random.choice(first_names_male)}",
            relation="father" if random.random() > 0.5 else "mother",
            phone=parent_phone
        )

        # StudentAddress
        StudentAddress.objects.create(
            organization=org,
            branch=branch,
            student=student,
            region="Toshkent shahri",
            district="Yunusobod tumani",
            address=student.address,
            parent_name=f"{lname} Valijon",
            parent_phone=parent_phone
        )

        created_count += 1

    final_count = Student.objects.filter(organization=org).count()
    print("=" * 60)
    print(f"Muvaffaqiyatli yakunlandi! Bazadagi jami o'quvchilar soni: {final_count} ta.")
    print("=" * 60)

if __name__ == "__main__":
    seed_students(114)
