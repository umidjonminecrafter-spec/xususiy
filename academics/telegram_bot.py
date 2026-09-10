import requests
from django.db.models import Q
from django.contrib.auth import get_user_model
from academics.models import Student, StudentGroup, Attendance, ExamResult, LessonSchedule

User = get_user_model()


def normalize_phone(phone_str):
    if not phone_str:
        return ""
    digits = "".join(c for c in str(phone_str) if c.isdigit())
    if len(digits) == 9:
        return f"+998{digits}"
    elif len(digits) == 12 and digits.startswith("998"):
        return f"+{digits}"
    elif len(digits) > 0:
        return f"+{digits}"
    return ""


def send_telegram_message(token, chat_id, text, reply_markup=None):
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        response = requests.post(url, json=payload, timeout=8)
        if response.status_code != 200:
            print(f"[TELEGRAM_API_ERROR] Status {response.status_code} sending to {chat_id}: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"[TELEGRAM_EXCEPTION] Error sending message to {chat_id}: {str(e)}")
        return False


STUDENT_BOT_TOKEN = "8987298254:AAEGTUlbiXG1_ZO41JnowqIRWkqVOxbB2iY"
REPORT_BOT_TOKEN = "8697561524:AAHyj2sGeNuYS5K8omuZoDdmtTBXz0Oob94"
STAFF_BOT_TOKEN = "8905500199:AAHcQuEV7k5IlvrZI7ixA8HNS_UZ8TRPgZA"


def get_student_bot_token(organization=None):
    from organizations.models import TelegramNotificationSetting
    if organization:
        setting = TelegramNotificationSetting.objects.filter(organization=organization).first()
        if setting and setting.student_bot_token:
            return setting.student_bot_token
    setting = TelegramNotificationSetting.objects.filter(student_bot_token__isnull=False).exclude(student_bot_token="").first()
    if setting and setting.student_bot_token:
        return setting.student_bot_token
    return STUDENT_BOT_TOKEN


def get_report_bot_token(organization=None):
    from organizations.models import TelegramNotificationSetting
    if organization:
        setting = TelegramNotificationSetting.objects.filter(organization=organization).first()
        if setting and setting.bot_token:
            return setting.bot_token
    setting = TelegramNotificationSetting.objects.filter(bot_token__isnull=False).exclude(bot_token="").first()
    if setting and setting.bot_token:
        return setting.bot_token
    return REPORT_BOT_TOKEN


def get_staff_bot_token(organization=None):
    from organizations.models import TelegramNotificationSetting
    if organization:
        setting = TelegramNotificationSetting.objects.filter(organization=organization).first()
        if setting and setting.staff_bot_token:
            return setting.staff_bot_token
    setting = TelegramNotificationSetting.objects.filter(staff_bot_token__isnull=False).exclude(staff_bot_token="").first()
    if setting and setting.staff_bot_token:
        return setting.staff_bot_token
    return STAFF_BOT_TOKEN


def get_parent_bot_token(organization=None):
    from organizations.models import TelegramNotificationSetting
    if organization:
        setting = TelegramNotificationSetting.objects.filter(organization=organization).first()
        if setting and setting.parent_bot_token:
            return setting.parent_bot_token
    setting = TelegramNotificationSetting.objects.filter(parent_bot_token__isnull=False).exclude(parent_bot_token="").first()
    if setting and setting.parent_bot_token:
        return setting.parent_bot_token
    return None


def get_verification_bot_token(organization=None):
    from organizations.models import TelegramNotificationSetting
    if organization:
        setting = TelegramNotificationSetting.objects.filter(organization=organization).first()
        if setting and setting.verification_bot_token:
            return setting.verification_bot_token
    setting = TelegramNotificationSetting.objects.filter(verification_bot_token__isnull=False).exclude(verification_bot_token="").first()
    if setting and setting.verification_bot_token:
        return setting.verification_bot_token
    return None


def get_support_bot_token(organization=None):
    from organizations.models import TelegramNotificationSetting
    if organization:
        setting = TelegramNotificationSetting.objects.filter(organization=organization).first()
        if setting and setting.support_bot_token:
            return setting.support_bot_token
    setting = TelegramNotificationSetting.objects.filter(support_bot_token__isnull=False).exclude(support_bot_token="").first()
    if setting and setting.support_bot_token:
        return setting.support_bot_token
    return None


def check_user_bot_registration(user):
    """
    Foydalanuvchi (Talaba, Ota-ona yoki Xodim) botdan ro'yxatdan o'tganligini tekshiradi
    """
    if not user:
        return False, "Foydalanuvchi topilmadi"

    chat_id = getattr(user, 'telegram_chat_id', None)
    if chat_id:
        return True, "Foydalanuvchi botdan ro'yxatdan o'tgan"

    # Agar Student bo'lsa, ota-onasini ham tekshiramiz
    f_chat = getattr(user, 'father_telegram_chat_id', None)
    m_chat = getattr(user, 'mother_telegram_chat_id', None)
    if f_chat or m_chat:
        return True, "Ota-onasi botdan ro'yxatdan o'tgan"

    return False, "Foydalanuvchi botdan ro'yxatdan o'tmagan"


def send_telegram_to_user(organization, user, text, reply_markup=None):
    if not user or not getattr(user, 'telegram_chat_id', None):
        return False

    chat_id = user.telegram_chat_id
    role = getattr(user, 'role', 'employee')

    if role == 'student':
        student_token = get_student_bot_token(organization)
        return send_telegram_message(student_token, chat_id, text, reply_markup)

    from organizations.models import TelegramNotificationSetting

    candidate_tokens = []
    org = organization or getattr(user, 'organization', None)

    if org:
        setting = TelegramNotificationSetting.objects.filter(organization=org).first()
        if setting:
            for t in [setting.staff_bot_token, setting.bot_token]:
                if t and t not in candidate_tokens:
                    candidate_tokens.append(t)

    for setting in TelegramNotificationSetting.objects.all():
        for t in [setting.staff_bot_token, setting.bot_token]:
            if t and t not in candidate_tokens:
                candidate_tokens.append(t)

    if STAFF_BOT_TOKEN not in candidate_tokens:
        candidate_tokens.append(STAFF_BOT_TOKEN)
    if REPORT_BOT_TOKEN not in candidate_tokens:
        candidate_tokens.append(REPORT_BOT_TOKEN)

    for token in candidate_tokens:
        if send_telegram_message(token, chat_id, text, reply_markup):
            return True

    return False


def get_contact_keyboard(text="📱 Telefon raqamni yuborish"):
    return {
        "keyboard": [[
            {
                "text": text,
                "request_contact": True
            }
        ]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }


def get_reply_keyboard(buttons):
    keyboard = []
    for row in buttons:
        row_buttons = []
        for btn in row:
            row_buttons.append({"text": btn})
        keyboard.append(row_buttons)
    return {
        "keyboard": keyboard,
        "resize_keyboard": True,
        "one_time_keyboard": False
    }


def seed_default_faqs(org_id):
    try:
        from support.models import FAQCategory, FAQItem
        category, _ = FAQCategory.objects.get_or_create(
            name="Umumiy",
            organization_id=org_id,
            defaults={"is_active": True}
        )
        
        defaults = [
            {
                "question": "Qanday ro'yxatdan o'taman?",
                "answer": "Saytning bosh sahifasidagi 'Ro'yxatdan o'tish' tugmasini bosing va ma'lumotlaringizni kiriting. Shundan so'ng administrator hisobingizni faollashtiradi.",
                "keywords": ["ro'yxatdan", "yangi", "akkaunt"]
            },
            {
                "question": "Kurs narxlari qancha?",
                "answer": "Kurs narxlari tanlangan yo'nalish va guruh turiga qarab farq qiladi. Narxlar haqida batafsil ma'lumotni 'Kurslar' bo'limidan olishingiz mumkin.",
                "keywords": ["narx", "kurslar", "qancha", "qiymat"]
            },
            {
                "question": "To'lov usullari qanday?",
                "answer": "To'lovlarni Click, Payme ilovalari orqali masofadan turib yoki o'quv markazi administratorining huzurida naqd / karta orqali to'lashingiz mumkin.",
                "keywords": ["to'lov", "click", "payme", "karta", "naqd"]
            },
            {
                "question": "Dars jadvalini qayerdan ko'raman?",
                "answer": "Dars jadvalini o'quvchi botidagi 'Dars jadvalim' bo'limidan yoki platformadagi shaxsiy kabinetingizga kirib ko'rishingiz mumkin.",
                "keywords": ["jadval", "darslar", "qachon"]
            },
            {
                "question": "Parol tiklash qanday bo'ladi?",
                "answer": "Tizimga kirish sahifasida 'Parolni unutdingizmi?' tugmasini bosing va telefon raqamingizni kiriting. Tasdiqlash kodi SMS orqali yuboriladi.",
                "keywords": ["parol", "tiklash", "unutdim"]
            },
            {
                "question": "Telefon raqamni qanday o'zgartiraman?",
                "answer": "Telefon raqamingizni o'zgartirish uchun o'quv markazi administratoriga murojaat qilishingiz kerak. Ular tizimda ma'lumotlaringizni yangilab berishadi.",
                "keywords": ["telefon", "raqam", "o'zgartirish"]
            },
            {
                "question": "Darslar qachon boshlanadi?",
                "answer": "Guruh to'lishi bilan darslar boshlanadi. Darslar boshlanish sanasi haqida guruh rahbari yoki bot orqali bildirishnoma olasiz.",
                "keywords": ["boshlanadi", "dars", "qachondan"]
            },
            {
                "question": "Qoldirilgan darslar to'lovi nima bo'ladi?",
                "answer": "Uzrli sabablarga ko'ra (kasallik varaqasi yoki shifokor ma'lumotnomasi bilan) qoldirilgan darslar uchun to'lov keyingi oyga ko'chiriladi.",
                "keywords": ["qoldirilgan", "kasal", "to'lov"]
            },
            {
                "question": "Sertifikat beriladimi?",
                "answer": "Ha, kursni muvaffaqiyatli yakunlab, yakuniy imtihonlardan o'tgan barcha o'quvchilarga maxsus sertifikat topshiriladi.",
                "keywords": ["sertifikat", "diplom", "hujjat"]
            },
            {
                "question": "Mobil ilova bormi?",
                "answer": "Hozirda platformaning to'liq funksional mobil versiyasi va Telegram botlari mavjud. Mobil ilova tez kunda ishga tushadi.",
                "keywords": ["mobil", "ilova", "app", "android", "ios"]
            },
            {
                "question": "Darslarni qayta ko'rish imkoni bormi?",
                "answer": "Ha, agar onlayn dars bo'lsa, dars yozib olinadi va shaxsiy kabinetingizda 1 oy davomida ko'rish uchun faol bo'ladi.",
                "keywords": ["qayta", "yozib", "video", "ko'rish"]
            },
            {
                "question": "Guruhni o'zgartirsa bo'ladimi?",
                "answer": "Ha, boshqa guruhda bo'sh joy mavjud bo'lsa, administrator bilan bog'lanib, guruhni almashtirishingiz mumkin.",
                "keywords": ["guruh", "o'zgartirish", "almashtirish"]
            },
            {
                "question": "O'quvchi reytingini qanday ko'raman?",
                "answer": "O'quvchi botidagi '🏆 Baholar' bo'limi orqali joriy baholar va guruhdagi umumiy reytingni kuzatib borishingiz mumkin.",
                "keywords": ["reyting", "baholar", "o'rin"]
            },
            {
                "question": "Davomatni qanday tekshiraman?",
                "answer": "O'quvchi yoki ota-ona botidagi '📊 Davomat' menyusi orqali barcha darslarga qatnashganlik holatini ko'rishingiz mumkin.",
                "keywords": ["davomat", "keldi", "kelmadi"]
            },
            {
                "question": "Onlayn va oflayn farqi nimada?",
                "answer": "Oflayn darslar o'quv markazimiz binosida, onlayn darslar esa platformamiz orqali jonli efir va video-darslar shaklida o'tiladi.",
                "keywords": ["onlayn", "oflayn", "farq", "masofaviy"]
            },
            {
                "question": "Bonus va chegirmalar bormi?",
                "answer": "Ha, bir vaqtning o'zida ikkita kursga qatnashganlar yoki bir oiladan bir necha kishi o'qiyotganlar uchun chegirmalar tizimi mavjud.",
                "keywords": ["chegirma", "bonus", "aksiyalar"]
            },
            {
                "question": "Ota-onalar uchun nazorat bormi?",
                "answer": "Ha, ota-onalar maxsus 'Ota-ona boti' orqali farzandlarining davomati, baholari va to'lovlarini to'liq nazorat qila oladilar.",
                "keywords": ["ota-ona", "nazorat", "farzand"]
            },
            {
                "question": "Sinov darslari bormi?",
                "answer": "Ha, har bir yo'nalish bo'yicha birinchi dars bepul sinov darsi hisoblanadi. Unda qatnashib, dars sifatini baholashingiz mumkin.",
                "keywords": ["sinov", "bepul", "birinchi", "dars"]
            },
            {
                "question": "Veb-sayt manzili qanday?",
                "answer": "Platformamizning rasmiy manzili: <a href='https://animated-malasada-239b8b.netlify.app/'>smarttalim.uz</a>. U yerda shaxsiy kabinetingizga kirishingiz mumkin.",
                "keywords": ["sayt", "vebsayt", "havola", "manzil"]
            },
            {
                "question": "Qo'shimcha darslar bormi?",
                "answer": "Ha, mavzuni o'zlashtirishda qiynalgan o'quvchilar uchun haftada bir marta bepul qo'shimcha konsultatsiya darslari tashkil etiladi.",
                "keywords": ["qo'shimcha", "konsultatsiya", "yordam"]
            }
        ]
        
        for item in defaults:
            FAQItem.objects.update_or_create(
                question=item["question"],
                organization_id=org_id,
                defaults={
                    "category": category,
                    "answer": item["answer"],
                    "keywords": item["keywords"],
                    "is_active": True
                }
            )
    except Exception as e:
        print(f"Error seeding FAQs: {str(e)}")


def get_support_faq_keyboard(org_id):
    from support.models import FAQItem
    if FAQItem.objects.filter(organization_id=org_id).count() < 10:
        seed_default_faqs(org_id)
        
    faqs = FAQItem.objects.filter(organization_id=org_id, is_active=True)
    buttons = []
    row = []
    for faq in faqs:
        row.append(faq.question)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append(["ℹ️ To'liqroq javob olish"])
    return get_reply_keyboard(buttons)


def get_support_ai_keyboard():
    return get_reply_keyboard([
        ["⬅️ Asosiy menyuga qaytish"],
        ["👤 Operator bilan bog'lanish"]
    ])



def find_users_by_phone(phone_raw, roles=None):
    """
    Har qanday formatdagi telefon raqam bo'yicha User larni topadi.
    Shuningdek Organization/Branch orqali ham qidiradi.
    """
    if not phone_raw:
        return User.objects.none()

    digits = "".join(c for c in str(phone_raw) if c.isdigit())
    if not digits:
        return User.objects.none()

    last9 = digits[-9:] if len(digits) >= 9 else digits
    norm = f"+998{last9}" if len(last9) == 9 else f"+{digits}"

    # 1. SQL ORM tezkor qidiruv
    q = Q(phone__icontains=last9) | Q(username__icontains=last9) | Q(phone=norm) | Q(phone=digits) | Q(phone=f"+{digits}")
    candidates = User.objects.filter(q)
    if roles:
        role_q = Q(role__in=roles) | Q(role__in=[r.upper() for r in roles]) | Q(role__in=[r.capitalize() for r in roles])
        if any(r in ['owner', 'admin'] for r in roles):
            role_q |= Q(is_superuser=True) | Q(is_staff=True)
        filtered = candidates.filter(role_q)
        if filtered.exists():
            return filtered

    # 2. Xotirada to'liq raqamlarni tozalab solishtirish (agar bazada "+998 90 123 45 67" kabi saqlangan bo'lsa)
    matched_ids = []
    for u in User.objects.all():
        u_p = "".join(c for c in str(u.phone or '') if c.isdigit())
        u_u = "".join(c for c in str(u.username or '') if c.isdigit())
        if (last9 and (u_p.endswith(last9) or u_u.endswith(last9))) or (digits and (u_p == digits or u_u == digits)):
            u_role = (u.role or '').lower()
            if not roles or u_role in roles or (any(r in ['owner', 'admin'] for r in roles) and (u.is_superuser or u.is_staff)):
                matched_ids.append(u.id)

    if matched_ids:
        return User.objects.filter(id__in=matched_ids)

    # 3. Agar User to'g'ridan-to'g'ri topilmasa, Organization yoki Branch telefon raqami orqali qidirish
    from organizations.models import Organization, Branch
    matched_org_ids = []
    for org in Organization.objects.all():
        org_p = "".join(c for c in str(org.phone or '') if c.isdigit())
        if (last9 and org_p.endswith(last9)) or (digits and org_p == digits):
            matched_org_ids.append(org.id)

    for br in Branch.objects.all():
        br_p = "".join(c for c in str(br.phone or '') if c.isdigit())
        if (last9 and br_p.endswith(last9)) or (digits and br_p == digits):
            if br.organization_id and br.organization_id not in matched_org_ids:
                matched_org_ids.append(br.organization_id)

    if matched_org_ids:
        org_users = User.objects.filter(organization_id__in=matched_org_ids)
        if roles:
            filtered_org_users = org_users.filter(
                Q(role__in=roles) | Q(role__in=[r.upper() for r in roles]) | Q(is_superuser=True) | Q(is_staff=True)
            )
            if filtered_org_users.exists():
                return filtered_org_users
        if org_users.exists():
            return org_users


    # 4. Agar rol cheklovisiz topilsa
    if roles:
        fallback_users = find_users_by_phone(phone_raw, roles=None)
        if fallback_users.exists():
            return fallback_users

    return User.objects.none()


def find_students_by_phone(phone_raw):
    if not phone_raw:
        return Student.objects.none()
    digits = "".join(c for c in str(phone_raw) if c.isdigit())
    if not digits:
        return Student.objects.none()
    last9 = digits[-9:] if len(digits) >= 9 else digits
    norm = f"+998{last9}" if len(last9) == 9 else f"+{digits}"

    q = Q(phone__icontains=last9) | Q(phone=norm) | Q(phone=digits) | Q(phone=f"+{digits}")
    st = Student.objects.filter(q)
    if st.exists():
        return st

    matched_ids = []
    for s in Student.objects.all():
        s_p = "".join(c for c in str(s.phone or '') if c.isdigit())
        if (last9 and s_p.endswith(last9)) or (digits and s_p == digits):
            matched_ids.append(s.id)
    if matched_ids:
        return Student.objects.filter(id__in=matched_ids)
    return Student.objects.none()


def find_parents_by_phone(phone_raw):
    if not phone_raw:
        return Student.objects.none(), Student.objects.none()
    digits = "".join(c for c in str(phone_raw) if c.isdigit())
    if not digits:
        return Student.objects.none(), Student.objects.none()
    last9 = digits[-9:] if len(digits) >= 9 else digits

    f_ids = []
    m_ids = []
    for s in Student.objects.all():
        f_p = "".join(c for c in str(s.father_phone or '') if c.isdigit())
        m_p = "".join(c for c in str(s.mother_phone or '') if c.isdigit())
        if (last9 and f_p.endswith(last9)) or (digits and f_p == digits):
            f_ids.append(s.id)
        if (last9 and m_p.endswith(last9)) or (digits and m_p == digits):
            m_ids.append(s.id)
    return Student.objects.filter(id__in=f_ids), Student.objects.filter(id__in=m_ids)


def handle_telegram_update(bot_type, token, update_data):
    """
    Stateless telegram update handler
    bot_type: 'verification', 'student', 'parent', 'staff', 'reports', 'support'
    """
    if not isinstance(update_data, dict):
        return

    # Callback query yoki oddiy message ni ajratib olamiz
    callback_query = update_data.get("callback_query")
    if callback_query:
        message = callback_query.get("message") or {}
        chat_id = message.get("chat", {}).get("id") or callback_query.get("from", {}).get("id")
        text = callback_query.get("data", "").strip()
        contact = None
    else:
        message = update_data.get("message") or update_data.get("edited_message") or {}
        if not message:
            return
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()
        contact = message.get("contact")

    if not chat_id:
        return

    # 1. Telefon raqam yuborilganda (kontakt yoki matn ko'rinishida) bog'lash
    phone_raw = None
    if contact:
        phone_raw = contact.get("phone_number")
    elif text and not text.startswith("/"):
        digits_only = "".join(c for c in text if c.isdigit())
        menu_prefixes = ["👤", "💰", "💳", "🧾", "📅", "📊", "🏆", "📝", "✉️", "👶", "📋", "🔔", "🌐", "🇺🇿", "🇷🇺", "⬅️", "ℹ️"]
        if (len(digits_only) >= 7 and len(digits_only) <= 15) and not any(text.startswith(btn) for btn in menu_prefixes):
            phone_raw = text

    if phone_raw:
        phone_normalized = normalize_phone(phone_raw)

        if bot_type == 'verification':
            students = find_students_by_phone(phone_raw)
            users = find_users_by_phone(phone_raw)

            linked = False
            if students.exists():
                students.update(telegram_chat_id=chat_id)
                linked = True
            if users.exists():
                users.update(telegram_chat_id=chat_id)
                linked = True

            if linked:
                msg = f"<b>Muvaffaqiyatli bog'landi!</b> 🔐\n\nTelefon raqam: {phone_normalized}\nUshbu bot orqali sizga kirish va parolni tiklash kodlari yuboriladi."
                send_telegram_message(token, chat_id, msg)
            else:
                msg = f"Kechirasiz, <code>{phone_normalized}</code> telefon raqami tizimda topilmadi. Iltimos, ma'muriyat bilan bog'laning."
                send_telegram_message(token, chat_id, msg, get_contact_keyboard())

        elif bot_type == 'student':
            students = find_students_by_phone(phone_raw)
            users = find_users_by_phone(phone_raw, roles=['student'])

            linked = False
            if students.exists():
                students.update(telegram_chat_id=chat_id)
                linked = True
            if users.exists():
                student_users = users.filter(role='student')
                if student_users.exists():
                    student_users.update(telegram_chat_id=chat_id)
                linked = True

            if linked:
                msg = f"<b>Muvaffaqiyatli bog'landi!</b> 🎓\n\nSiz Student botidan muvaffaqiyatli ro'yxatdan o'tdingiz."
                menu = get_reply_keyboard([
                    ["👤 Profilim", "💰 Balans & Qarz"],
                    ["💳 Oxirgi to'lovlar", "🧾 Oxirgi to'lov cheki"],
                    ["📅 Dars jadvalim", "📊 Davomatlarim"],
                    ["🏆 Imtihon baholari", "📝 Uy vazifalarim"],
                    ["✉️ Kelgan xabarlar"]
                ])
                send_telegram_message(token, chat_id, msg, menu)
            else:
                msg = f"Kechirasiz, <code>{phone_normalized}</code> telefon raqamli talaba tizimda topilmadi."
                send_telegram_message(token, chat_id, msg, get_contact_keyboard())

        elif bot_type == 'parent':
            students_father, students_mother = find_parents_by_phone(phone_raw)

            linked = False
            if students_father.exists():
                students_father.update(father_telegram_chat_id=chat_id)
                linked = True
            if students_mother.exists():
                students_mother.update(mother_telegram_chat_id=chat_id)
                linked = True

            if linked:
                msg = f"<b>Muvaffaqiyatli bog'landi!</b> 👨‍👩‍👧‍👦\n\nSiz Ota-ona botidan muvaffaqiyatli ro'yxatdan o'tdingiz."
                menu = get_reply_keyboard([["👶 Farzandlarim", "📊 Davomat"], ["🏆 Baholar", "💳 To'lovlar"]])
                send_telegram_message(token, chat_id, msg, menu)
            else:
                msg = f"Kechirasiz, <code>{phone_normalized}</code> telefon raqamli ota-ona tizimda topilmadi."
                send_telegram_message(token, chat_id, msg, get_contact_keyboard())

        elif bot_type == 'reports':
            users = find_users_by_phone(phone_raw, roles=['owner', 'admin'])
            from organizations.models import Organization, TelegramNotificationSetting

            orgs_found = []
            if users.exists():
                users.update(telegram_chat_id=chat_id)
                for u in users:
                    if u.organization and u.organization not in orgs_found:
                        orgs_found.append(u.organization)

            # Agar foydalanuvchiga to'g'ridan-to'g'ri tashkilot bog'lanmagan bo'lsa:
            if not orgs_found:
                digits = "".join(c for c in str(phone_raw) if c.isdigit())
                last9 = digits[-9:] if len(digits) >= 9 else digits
                matched_orgs = []
                for org in Organization.objects.all():
                    org_p = "".join(c for c in str(org.phone or '') if c.isdigit())
                    if (last9 and org_p.endswith(last9)) or (digits and org_p == digits):
                        matched_orgs.append(org)

                if matched_orgs:
                    for o in matched_orgs:
                        if o not in orgs_found:
                            orgs_found.append(o)
                        # Shu tashkilotning admin/owner userlariga chat_id ni bog'lash
                        u_list = User.objects.filter(organization=o)
                        target_users = u_list.filter(Q(role__in=['owner', 'admin']) | Q(is_superuser=True) | Q(is_staff=True))
                        if not target_users.exists():
                            target_users = u_list
                        if target_users.exists():
                            target_users.update(telegram_chat_id=chat_id)
                        else:
                            # User mavjud bo'lmasa yaratib bog'laymiz
                            username = f"{digits}_{o.id}"
                            new_u, _ = User.objects.get_or_create(
                                username=username,
                                defaults={'phone': phone_normalized, 'role': 'owner', 'organization': o, 'telegram_chat_id': chat_id}
                            )
                            new_u.telegram_chat_id = chat_id
                            new_u.save()

            # Agar tizimda faqat bitta tashkilot bo'lsa va user admin bo'lsa
            if not orgs_found and users.exists():
                first_org = Organization.objects.first()
                if first_org:
                    orgs_found.append(first_org)
                    users.filter(organization__isnull=True).update(organization=first_org)

            if orgs_found:
                org_names = []
                for org in orgs_found:
                    org_names.append(org.name)
                    setting, _ = TelegramNotificationSetting.objects.get_or_create(organization=org)
                    cids = set(c.strip() for c in (setting.chat_ids or '').replace(',', ' ').split() if c.strip())
                    cids.add(str(chat_id))
                    setting.chat_ids = ", ".join(cids)
                    if not setting.bot_token:
                        setting.bot_token = token
                    setting.save(update_fields=['chat_ids', 'bot_token'])

                orgs_display = ", ".join(set(org_names))
                msg = (
                    f"<b>Muvaffaqiyatli bog'landi! 📊</b>\n\n"
                    f"🏢 Tashkilot: <b>{orgs_display}</b>\n"
                    f"📱 Telefon: <code>{phone_normalized}</code>\n\n"
                    f"Siz Hisobotlar botidan muvaffaqiyatli ro'yxatdan o'tdingiz.\n"
                    f"Endi <b>{orgs_display}</b> ning barcha moliyaviy ma'lumotlari va kunlik hisobotlari ushbu botga keladi.\n\n"
                    f"Iltimos, bot tilini tanlang:\n"
                    f"Пожалуйста, выберите язык бота:"
                )
                menu = get_reply_keyboard([["🇺🇿 O'zbekcha", "🇷🇺 Русский"]])
                send_telegram_message(token, chat_id, msg, menu)
            else:
                msg = f"Kechirasiz, <code>{phone_normalized}</code> raqamiga biriktirilgan tashkilot topilmadi.\nIltimos, ma'muriyat bilan bog'laning."
                send_telegram_message(token, chat_id, msg, get_contact_keyboard())


        elif bot_type == 'staff':
            users = find_users_by_phone(phone_raw, roles=['teacher', 'administrator', 'manager', 'accountant', 'staff', 'owner', 'admin'])
            if users.exists():
                users.update(telegram_chat_id=chat_id)
                msg = (
                    "<b>Muvaffaqiyatli bog'landi! 💼</b>\n\n"
                    "Iltimos, bot tilini tanlang:\n"
                    "Пожалуйста, выберите язык бота:"
                )
                menu = get_reply_keyboard([["🇺🇿 O'zbekcha", "🇷🇺 Русский"]])
                send_telegram_message(token, chat_id, msg, menu)
            else:
                msg = f"Kechirasiz, <code>{phone_normalized}</code> telefon raqamli xodim topilmadi."
                send_telegram_message(token, chat_id, msg, get_contact_keyboard())
        return



    # 2. Buyruqlar yoki menyu tugmalarini bosganda
    if text == "/start":
        # 🌟 Yangi: Agar foydalanuvchi allaqachon bog'langan bo'lsa menyuni qayta yuborish
        if bot_type == 'student' and Student.objects.filter(telegram_chat_id=chat_id).exists():
            student = Student.objects.filter(telegram_chat_id=chat_id).first()
            msg = f"Assalomu alaykum, {student.first_name}! Xush kelibsiz."
            menu = get_reply_keyboard([
                ["👤 Profilim", "💰 Balans & Qarz"],
                ["💳 Oxirgi to'lovlar", "🧾 Oxirgi to'lov cheki"],
                ["📅 Dars jadvalim", "📊 Davomatlarim"],
                ["🏆 Imtihon baholari", "📝 Uy vazifalarim"],
                ["✉️ Kelgan xabarlar"]
            ])
            send_telegram_message(token, chat_id, msg, menu)
            return
        elif bot_type == 'reports' and User.objects.filter(telegram_chat_id=chat_id).exists():
            user = User.objects.filter(telegram_chat_id=chat_id).first()
            lang = getattr(user, 'telegram_language', 'uz') or 'uz'
            if lang == 'ru':
                msg = f"Здравствуйте, {user.get_full_name() or user.username}! Добро пожаловать в бот отчетов."
                menu = get_reply_keyboard([
                    ["👤 Мой профиль", "📊 Дневной отчет"],
                    ["🌐 Сменить язык"]
                ])
            else:
                msg = f"Assalomu alaykum, {user.get_full_name() or user.username}! Hisobotlar botiga xush kelibsiz."
                menu = get_reply_keyboard([
                    ["👤 Profilim", "📊 Kunlik Hisobot"],
                    ["🌐 Tilni o'zgartirish"]
                ])
            send_telegram_message(token, chat_id, msg, menu)
            return
        elif bot_type == 'staff' and User.objects.filter(telegram_chat_id=chat_id).exclude(role='student').exists():
            user = User.objects.filter(telegram_chat_id=chat_id).exclude(role='student').first()
            lang = getattr(user, 'telegram_language', 'uz') or 'uz'
            if lang == 'ru':
                msg = f"Здравствуйте, {user.get_full_name() or user.username}! Добро пожаловать."
                menu = get_reply_keyboard([
                    ["👤 Мой профиль", "📅 Мое расписание"],
                    ["📋 Мои задачи", "💰 Зарплата и расчеты"],
                    ["🔔 Уведомления", "🌐 Сменить язык"]
                ])
            else:
                msg = f"Assalomu alaykum, {user.get_full_name() or user.username}! Xush kelibsiz."
                menu = get_reply_keyboard([
                    ["👤 Profilim", "📅 Kunlik dars jadvalim"],
                    ["📋 Mening vazifalarim", "💰 Oylik va hisoblar"],
                    ["🔔 Bildirishnomalar", "🌐 Tilni o'zgartirish"]
                ])
            send_telegram_message(token, chat_id, msg, menu)
            return
        elif bot_type == 'parent' and Student.objects.filter(Q(father_telegram_chat_id=chat_id) | Q(mother_telegram_chat_id=chat_id)).exists():
            msg = "Assalomu alaykum! Xush kelibsiz."
            menu = get_reply_keyboard([["👶 Farzandlarim", "📊 Davomat"], ["🏆 Baholar", "💳 To'lovlar"]])
            send_telegram_message(token, chat_id, msg, menu)
            return
        elif bot_type == 'support':
            from organizations.models import TelegramNotificationSetting
            setting = TelegramNotificationSetting.objects.filter(support_bot_token=token).first()
            if not setting:
                setting = TelegramNotificationSetting.objects.first()
            
            org_id = setting.organization_id if setting else 1
            menu = get_support_faq_keyboard(org_id)
            
            msg = "Assalomu alaykum! Yordam markazi botiga xush kelibsiz. Quyidagi savollardan birini tanlang yoki savolingizni yozib qoldiring:"
            send_telegram_message(token, chat_id, msg, menu)
            return

        msg = "Assalomu alaykum! SmartTalim xizmatiga xush kelibsiz.\n\nBotdan foydalanish uchun telefon raqamingizni yuboring:"
        send_telegram_message(token, chat_id, msg, get_contact_keyboard())
        return

    # Tekshiruv: Akkaunt bog'langanligini aniqlash
    if bot_type == 'verification':
        # Verifikatsiya botida menyu yo'q, faqat telefon so'rash bo'ladi
        msg = "Siz botdan muvaffaqiyatli ro'yxatdan o'tgan ekansiz. Parolni tiklash kodi kerak bo'lganda shu yerga yuboriladi. 🔐"
        send_telegram_message(token, chat_id, msg)

    elif bot_type == 'support':
        from organizations.models import TelegramNotificationSetting
        setting = TelegramNotificationSetting.objects.filter(support_bot_token=token).first()
        if not setting:
            setting = TelegramNotificationSetting.objects.first()
            
        if setting:
            org_id = setting.organization_id
            
            # 1. Back to Main Menu
            if text == "⬅️ Asosiy menyuga qaytish":
                menu = get_support_faq_keyboard(org_id)
                msg = "Asosiy menyuga qaytdingiz. Quyidagi savollardan birini tanlang yoki savolingizni yozing:"
                send_telegram_message(token, chat_id, msg, menu)
                return
                
            # 2. Get More Detailed Answer (Connect to AI)
            elif text == "ℹ️ To'liqroq javob olish":
                menu = get_support_ai_keyboard()
                msg = "Siz sun'iy intellekt yordamchisiga ulandingiz. Savolingizni bot ichida yozib yuboring, u javob beradi."
                send_telegram_message(token, chat_id, msg, menu)
                return
                
            # 3. Connect to Live Operator
            elif text == "👤 Operator bilan bog'lanish":
                from support.services.chat import AIChatService
                # Create chat session & ticket in the background
                session = AIChatService.get_or_create_session(telegram_chat_id=str(chat_id), organization_id=org_id)
                from support.services.ticket import TicketService
                ticket = TicketService.auto_create_ticket(session, description="Foydalanuvchi operator bilan bog'lanish tugmasini bosdi.")
                
                contact_link = getattr(setting, 'support_contact_link', None)
                if contact_link:
                    username = contact_link.replace('@', '').strip()
                    operator_url = f"https://t.me/{username}"
                else:
                    operator_url = "https://t.me/umidjonminecrafter" # Fallback
                
                reply = (
                    f"Sizni operatorga ulayapman. Iltimos kuting...\n\n"
                    f"[Tizim]: Sizning so'rovingiz bo'yicha operatorlarimiz uchun yordam chiptasi ochildi (Chipta #{ticket.id}).\n\n"
                    f"Operator bilan to'g'ridan-to'g'ri bog'lanish uchun quyidagi havolani bosing:\n"
                    f"👉 <a href='{operator_url}'>Operator bilan bog'lanish</a>"
                )
                menu = get_support_ai_keyboard()
                send_telegram_message(token, chat_id, reply, menu)
                return
            
            # 4. Standard text messages processing
            else:
                # Check for exact FAQ question match first
                from support.models import FAQItem
                faq_match = FAQItem.objects.filter(
                    organization_id=org_id,
                    question__iexact=text.strip(),
                    is_active=True
                ).first()
                
                if faq_match:
                    reply = faq_match.answer
                    menu = get_support_faq_keyboard(org_id)
                else:
                    # Fallback to AI Chat pipeline
                    from support.services.chat import AIChatService
                    reply = AIChatService.handle_telegram_chat(
                        chat_id=str(chat_id),
                        message=text,
                        organization_id=org_id
                    )
                    # If AI created a ticket due to low confidence, append operator contact link
                    if "chiptasi ochildi" in reply:
                        contact_link = getattr(setting, 'support_contact_link', None)
                        if contact_link:
                            username = contact_link.replace('@', '').strip()
                            operator_url = f"https://t.me/{username}"
                        else:
                            operator_url = "https://t.me/umidjonminecrafter" # Fallback
                        reply += f"\n\nTo'g'ridan-to'g'ri bog'lanish uchun:\n👉 <a href='{operator_url}'>Operator bilan bog'lanish (Telegram)</a>"
                    
                    menu = get_support_ai_keyboard()
                
                send_telegram_message(token, chat_id, reply, menu)

    elif bot_type == 'student':
        student = Student.objects.filter(telegram_chat_id=chat_id).first()
        if not student:
            msg = "Siz hali ro'yxatdan o'tmagansiz. Iltimos, telefon raqamingizni yuboring:"
            send_telegram_message(token, chat_id, msg, get_contact_keyboard())
            return

        menu = get_reply_keyboard([
            ["👤 Profilim", "💰 Balans & Qarz"],
            ["💳 Oxirgi to'lovlar", "🧾 Oxirgi to'lov cheki"],
            ["📅 Dars jadvalim", "📊 Davomatlarim"],
            ["🏆 Imtihon baholari", "📝 Uy vazifalarim"],
            ["✉️ Kelgan xabarlar"]
        ])

        if text == "👤 Profilim":
            active_groups = StudentGroup.objects.filter(student=student, group__status='active')
            groups_str = ", ".join([g.group.name for g in active_groups]) or "Guruh yo'q"
            res = (
                f"<b>👤 Talaba Profili</b>\n\n"
                f"Ism: {student.first_name} {student.last_name or ''}\n"
                f"Telefon: {student.phone}\n"
                f"Guruhlar: {groups_str}\n"
                f"Balans: {int(student.balance or 0):,} UZS\n".replace(",", " ")
            )
            send_telegram_message(token, chat_id, res, menu)

        elif text in ["💰 Balansim", "💰 Balans & Qarz"]:
            bal = student.balance or 0
            status_emoji = "✅" if bal >= 0 else "⚠️"
            debt = abs(bal) if bal < 0 else 0
            res = (
                f"<b>💰 Balans va Qarz holati:</b>\n\n"
                f"Joriy balans: <code>{int(bal):,} UZS</code> {status_emoji}\n"
                f"Qarzdorlik: <code>{int(debt):,} UZS</code>\n"
                f"To'lov kuni: {student.payment_date or 'Belgilanmagan'}"
            ).replace(",", " ")
            send_telegram_message(token, chat_id, res, menu)

        elif text == "💳 Oxirgi to'lovlar":
            from finance.models import Payment
            payments = Payment.objects.filter(student=student).order_by('-date')[:5]
            if not payments.exists():
                res = "Sizda to'lovlar tarixi topilmadi."
            else:
                res = "<b>💳 Oxirgi 5 ta to'lovingiz:</b>\n\n"
                for p in payments:
                    res += f"• {p.date}: <b>{int(p.amount or 0):,} UZS</b> ({p.payment_method})\n"
                res = res.replace(",", " ")
            send_telegram_message(token, chat_id, res, menu)

        elif text == "🧾 Oxirgi to'lov cheki":
            from finance.models import Payment
            p = Payment.objects.filter(student=student).order_by('-date').first()
            if not p:
                res = "Oxirgi to'lov cheki topilmadi."
            else:
                org_name = student.organization.name if student.organization else "SmartTalim"
                employee_name = p.employee.get_full_name() or p.employee.username if p.employee else "Tizim"
                res = (
                    f"<b>🧾 To'lov Cheki #{p.id}</b>\n"
                    f"🏢 Muassasa: <b>{org_name}</b>\n\n"
                    f"👤 Talaba: {student.first_name} {student.last_name or ''}\n"
                    f"💵 Summa: <code>{int(p.amount or 0):,} UZS</code>\n"
                    f"📅 Sana: {p.date}\n"
                    f"💳 To'lov turi: {p.payment_method}\n"
                    f"🧑‍💼 Qabul qildi: {employee_name}\n"
                    f"💬 Izoh: {p.comment or '-'}\n\n"
                    f"<i>SmartTalim tizimi orqali tasdiqlangan.</i>"
                ).replace(",", " ")
            send_telegram_message(token, chat_id, res, menu)

        elif text == "📅 Dars jadvalim":
            active_groups = StudentGroup.objects.filter(student=student, group__status='active')
            if not active_groups.exists():
                send_telegram_message(token, chat_id, "Siz faol guruhlarda topilmadingiz.", menu)
                return

            res = "<b>📅 Sizning dars jadvalingiz:</b>\n\n"
            for sg in active_groups:
                g = sg.group
                day_type_str = "Juft kunlar" if g.day_type == 'even' else "Toq kunlar"
                teacher_str = g.teacher.get_full_name() if g.teacher else "Noma'lum"
                res += (
                    f"📚 <b>{g.name}</b> ({g.course.name if g.course else ''})\n"
                    f"⏰ Vaqt: {g.start_time or 'Belgilanmagan'}\n"
                    f"🗓 Kunlar: {day_type_str}\n"
                    f"👤 O'qituvchi: {teacher_str}\n\n"
                )
            send_telegram_message(token, chat_id, res, menu)

        elif text == "📊 Davomatlarim":
            attendances = Attendance.objects.filter(student=student).order_by('-date')[:10]
            if not attendances.exists():
                res = "Davomat ma'lumotlari topilmadi."
            else:
                res = "<b>📊 Oxirgi 10 ta davomatingiz:</b>\n\n"
                for att in attendances:
                    status_text = "Keldi ✅" if att.status == 'present' else "Kelmadi ❌" if att.status == 'absent' else "Kechikdi ⚠️" if att.status == 'late' else "Sababli 📁"
                    res += f"• {att.date}: {att.group.name} - <b>{status_text}</b>\n"
            send_telegram_message(token, chat_id, res, menu)

        elif text == "🏆 Imtihon baholari":
            results = ExamResult.objects.filter(student=student).select_related('exam').order_by('-exam__date')[:10]
            if not results.exists():
                res = "Baholar topilmadi."
            else:
                res = "<b>🏆 Oxirgi imtihon baholaringiz:</b>\n\n"
                for r in results:
                    res += f"• {r.exam.name} ({r.exam.date}): <b>{int(r.score or 0)} ball</b>\n"
            send_telegram_message(token, chat_id, res, menu)

        elif text == "📝 Uy vazifalarim":
            from academics.models import Homework
            active_groups = StudentGroup.objects.filter(student=student, group__status='active').values_list('group_id', flat=True)
            homeworks = Homework.objects.filter(group_id__in=active_groups).order_by('-due_date')[:5]
            if not homeworks.exists():
                res = "Uy vazifalari topilmadi."
            else:
                res = "<b>📝 Uy vazifalari va topshiriqlar:</b>\n\n"
                for hw in homeworks:
                    due = hw.due_date.strftime("%d.%m.%Y") if hw.due_date else "Belgilanmagan"
                    res += (
                        f"📚 <b>{hw.group.name}</b>: <u>{hw.title}</u>\n"
                        f"💬 Topshiriq: {hw.text or 'Matn kiritilmagan'}\n"
                        f"📅 Muddat: <b>{due}</b>\n\n"
                    )
            send_telegram_message(token, chat_id, res, menu)

        elif text == "✉️ Kelgan xabarlar":
            from communication.models import SMSMessages
            sms_list = SMSMessages.objects.filter(recipient=student.phone).order_by('-sent_at')[:5]
            if not sms_list.exists():
                res = "Sizga yuborilgan xabarlar topilmadi."
            else:
                res = "<b>✉️ Oxirgi 5 ta kelgan tizim xabarlari:</b>\n\n"
                for sms in sms_list:
                    date_str = sms.sent_at.strftime("%d.%m.%Y %H:%M")
                    res += f"📅 {date_str}\n💬 {sms.message}\n\n"
            send_telegram_message(token, chat_id, res, menu)

        else:
            send_telegram_message(token, chat_id, "Noma'lum buyruq. Iltimos menyudan foydalaning.", menu)

    elif bot_type == 'parent':
        students = Student.objects.filter(Q(father_telegram_chat_id=chat_id) | Q(mother_telegram_chat_id=chat_id))
        if not students.exists():
            msg = "Siz hali ro'yxatdan o'tmagansiz. Iltimos, telefon raqamingizni yuboring:"
            send_telegram_message(token, chat_id, msg, get_contact_keyboard())
            return

        menu = get_reply_keyboard([["👶 Farzandlarim", "📊 Davomat"], ["🏆 Baholar", "💳 To'lovlar"]])

        if text == "👶 Farzandlarim":
            res = "<b>👶 Farzandlaringiz ro'yxati:</b>\n\n"
            for s in students:
                active_groups = StudentGroup.objects.filter(student=s, group__status='active')
                groups_str = ", ".join([g.group.name for g in active_groups]) or "Guruh yo'q"
                res += (
                    f"👦 <b>{s.first_name} {s.last_name or ''}</b>\n"
                    f"Balans: {int(s.balance or 0):,} UZS\n"
                    f"Guruhlar: {groups_str}\n\n"
                ).replace(",", " ")
            send_telegram_message(token, chat_id, res, menu)

        elif text == "📊 Davomat":
            res = "<b>📊 Oxirgi darslardagi davomat:</b>\n\n"
            for s in students:
                res += f"👦 <b>{s.first_name}:</b>\n"
                attendances = Attendance.objects.filter(student=s).order_by('-date')[:10]
                if not attendances.exists():
                    res += "  Davomatlar topilmadi.\n\n"
                    continue
                for att in attendances:
                    status_text = "Keldi ✅" if att.status == 'present' else "Kelmadi ❌" if att.status == 'absent' else "Kechikdi ⚠️" if att.status == 'late' else "Sababli 📁"
                    res += f"  • {att.date}: {att.group.name} - <b>{status_text}</b>\n"
                res += "\n"
            send_telegram_message(token, chat_id, res, menu)

        elif text == "🏆 Baholar":
            res = "<b>🏆 Imtihon baholari:</b>\n\n"
            for s in students:
                res += f"👦 <b>{s.first_name}:</b>\n"
                results = ExamResult.objects.filter(student=s).select_related('exam').order_by('-exam__date')
                if not results.exists():
                    res += "  Baholar topilmadi.\n\n"
                    continue
                for r in results:
                    res += f"  • {r.exam.name} ({r.exam.date}): <b>{int(r.score or 0)} ball</b>\n"
                res += "\n"
            send_telegram_message(token, chat_id, res, menu)

        elif text == "💳 To'lovlar":
            res = "<b>💳 To'lovlar va balans holati:</b>\n\n"
            for s in students:
                bal = s.balance or 0
                status_text = "Faol ✅" if bal >= 0 else "Qarzdorlik bor ⚠️"
                res += (
                    f"👦 <b>{s.first_name}:</b>\n"
                    f"  Joriy balans: <code>{int(bal):,} UZS</code>\n"
                    f"  Holat: {status_text}\n"
                    f"  Keyingi to'lov sanasi: {s.payment_date or 'Belgilanmagan'}\n\n"
                ).replace(",", " ")
            send_telegram_message(token, chat_id, res, menu)

        else:
            send_telegram_message(token, chat_id, "Noma'lum buyruq. Iltimos menyudan foydalaning.", menu)

    elif bot_type == 'reports':
        user = User.objects.filter(telegram_chat_id=chat_id).filter(
            Q(role__iexact='owner') | Q(role__iexact='admin') | Q(is_superuser=True) | Q(is_staff=True)
        ).first()
        if not user:
            user = User.objects.filter(telegram_chat_id=chat_id).first()
        if not user:
            msg = "Kechirasiz, ushbu botga faqat tashkilot rahbarlari kira oladi. Telefon raqamingizni yuboring:"
            send_telegram_message(token, chat_id, msg, get_contact_keyboard())
            return


        lang = getattr(user, 'telegram_language', 'uz') or 'uz'

        # Menyu
        if lang == 'ru':
            menu = get_reply_keyboard([
                ["👤 Мой профиль", "📊 Дневной отчет"],
                ["🌐 Сменить язык"]
            ])
        else:
            menu = get_reply_keyboard([
                ["👤 Profilim", "📊 Kunlik Hisobot"],
                ["🌐 Tilni o'zgartirish"]
            ])

        if text == "🇺🇿 O'zbekcha":
            user.telegram_language = 'uz'
            user.save()
            msg = "Til tanlandi: O'zbekcha! 🇺🇿"
            menu = get_reply_keyboard([
                ["👤 Profilim", "📊 Kunlik Hisobot"],
                ["🌐 Tilni o'zgartirish"]
            ])
            send_telegram_message(token, chat_id, msg, menu)
            return

        elif text == "🇷🇺 Русский":
            user.telegram_language = 'ru'
            user.save()
            msg = "Язык выбран: Русский! 🇷🇺"
            menu = get_reply_keyboard([
                ["👤 Мой профиль", "📊 Дневной отчет"],
                ["🌐 Сменить язык"]
            ])
            send_telegram_message(token, chat_id, msg, menu)
            return

        elif text in ["🌐 Tilni o'zgartirish", "🌐 Сменить язык"]:
            msg = "Tilni tanlang / Выберите язык:"
            menu = get_reply_keyboard([["🇺🇿 O'zbekcha", "🇷🇺 Русский"]])
            send_telegram_message(token, chat_id, msg, menu)
            return

        elif text in ["👤 Profilim", "👤 Мой профиль"]:
            from organizations.models import TelegramNotificationSetting
            org_names = []
            if user.organization:
                org_names.append(user.organization.name)
            for s in TelegramNotificationSetting.objects.all():
                cids = set(c.strip() for c in (s.chat_ids or '').replace(',', ' ').split() if c.strip())
                if str(chat_id) in cids and s.organization:
                    org_names.append(s.organization.name)

            org_display = ", ".join(set(org_names)) or "SmartTalim"

            if lang == 'ru':
                res = (
                    f"<b>👤 Профиль Руководителя</b>\n\n"
                    f"Имя: <b>{user.get_full_name() or user.username}</b>\n"
                    f"Должность: <b>{user.get_role_display()}</b>\n"
                    f"🏢 Организация: <b>{org_display}</b>\n"
                    f"Телефон: <code>{user.phone or 'Не указан'}</code>\n"
                )
            else:
                res = (
                    f"<b>👤 Rahbar Profili</b>\n\n"
                    f"Ism: <b>{user.get_full_name() or user.username}</b>\n"
                    f"Lavozim: <b>{user.get_role_display()}</b>\n"
                    f"🏢 Tashkilot: <b>{org_display}</b>\n"
                    f"Telefon: <code>{user.phone or 'Kiritilmagan'}</code>\n"
                )
            send_telegram_message(token, chat_id, res, menu)

        elif text in ["📊 Kunlik Hisobot", "📊 Дневной отчет"]:
            from django.utils import timezone
            from datetime import timedelta
            from academics.tasks import generate_daily_report_message
            from organizations.models import Organization, TelegramNotificationSetting

            orgs_to_report = []
            if user.organization:
                orgs_to_report.append(user.organization)

            for s in TelegramNotificationSetting.objects.all():
                cids = set(c.strip() for c in (s.chat_ids or '').replace(',', ' ').split() if c.strip())
                if str(chat_id) in cids and s.organization and s.organization not in orgs_to_report:
                    orgs_to_report.append(s.organization)

            if not orgs_to_report and Organization.objects.exists():
                orgs_to_report.append(Organization.objects.first())

            if orgs_to_report:
                yesterday = (timezone.now() - timedelta(days=1)).date()
                for org in orgs_to_report:
                    try:
                        report_msg = generate_daily_report_message(org, yesterday, lang=lang)
                        send_telegram_message(token, chat_id, report_msg, menu)
                    except Exception as e:
                        err_msg = f"[{org.name}] Hisobot shakllantirishda xatolik: {str(e)}" if lang == 'uz' else f"[{org.name}] Ошибка формирования отчета: {str(e)}"
                        send_telegram_message(token, chat_id, err_msg, menu)
            else:
                err_msg = "Tashkilotingiz aniqlanmadi." if lang == 'uz' else "Ваша организация не определена."
                send_telegram_message(token, chat_id, err_msg, menu)


        else:
            err_msg = "Noma'lum buyruq. Iltimos menyudan foydalaning." if lang == 'uz' else "Неизвестная команда. Пожалуйста, используйте меню."
            send_telegram_message(token, chat_id, err_msg, menu)

    elif bot_type == 'staff':
        user = User.objects.filter(telegram_chat_id=chat_id).exclude(role='student').first()
        if not user:
            msg = "Siz hali ro'yxatdan o'tmagansiz. Iltimos, telefon raqamingizni yuboring:"
            send_telegram_message(token, chat_id, msg, get_contact_keyboard())
            return

        lang = getattr(user, 'telegram_language', 'uz') or 'uz'

        # Defolt xodimlar menyusi
        if lang == 'ru':
            menu = get_reply_keyboard([
                ["👤 Мой профиль", "📅 Мое расписание"],
                ["📋 Мои задачи", "💰 Зарплата и расчеты"],
                ["🔔 Уведомления", "🌐 Сменить язык"]
            ])
        else:
            menu = get_reply_keyboard([
                ["👤 Profilim", "📅 Kunlik dars jadvalim"],
                ["📋 Mening vazifalarim", "💰 Oylik va hisoblar"],
                ["🔔 Bildirishnomalar", "🌐 Tilni o'zgartirish"]
            ])

        if text == "🇺🇿 O'zbekcha":
            user.telegram_language = 'uz'
            user.save()
            msg = "Til tanlandi: O'zbekcha! 🇺🇿"
            menu = get_reply_keyboard([
                ["👤 Profilim", "📅 Kunlik dars jadvalim"],
                ["📋 Mening vazifalarim", "💰 Oylik va hisoblar"],
                ["🔔 Bildirishnomalar", "🌐 Tilni o'zgartirish"]
            ])
            send_telegram_message(token, chat_id, msg, menu)
            return

        elif text == "🇷🇺 Русский":
            user.telegram_language = 'ru'
            user.save()
            msg = "Язык выбран: Русский! 🇷🇺"
            menu = get_reply_keyboard([
                ["👤 Мой профиль", "📅 Мое расписание"],
                ["📋 Мои задачи", "💰 Зарплата и расчеты"],
                ["🔔 Уведомления", "🌐 Сменить язык"]
            ])
            send_telegram_message(token, chat_id, msg, menu)
            return

        elif text in ["🌐 Tilni o'zgartirish", "🌐 Сменить язык"]:
            msg = "Tilni tanlang / Выберите язык:"
            menu = get_reply_keyboard([["🇺🇿 O'zbekcha", "🇷🇺 Русский"]])
            send_telegram_message(token, chat_id, msg, menu)
            return

        elif text in ["👤 Profilim", "👤 Мой профиль"]:
            groups = StudentGroup.objects.filter(group__teacher=user, group__status='active').values('group__name',
                                                                                                     'group__course__name').distinct()
            groups_str = ", ".join(
                [f"{g['group__name']} ({g['group__course__name']})" for g in groups]) or ("Guruh biriktirilmagan" if lang == 'uz' else "Группы не привязаны")
            if lang == 'ru':
                res = (
                    f"<b>👤 Профиль сотрудника</b>\n\n"
                    f"Имя: {user.get_full_name() or user.username}\n"
                    f"Должность: {user.get_role_display()}\n"
                    f"Телефон: {user.phone or 'Не указан'}\n"
                    f"Группы: {groups_str}\n"
                )
            else:
                res = (
                    f"<b>👤 Xodim profili</b>\n\n"
                    f"Ism: {user.get_full_name() or user.username}\n"
                    f"Lavozim: {user.get_role_display()}\n"
                    f"Telefon: {user.phone or 'Kiritilmagan'}\n"
                    f"O'qitadigan guruhlar: {groups_str}\n"
                )
            send_telegram_message(token, chat_id, res, menu)

        elif text in ["📅 Kunlik dars jadvalim", "📅 Мое расписание"]:
            schedules = LessonSchedule.objects.filter(teacher=user).select_related('group', 'group__course')
            if not schedules.exists():
                err_msg = "Kunlik dars jadvallari topilmadi." if lang == 'uz' else "Расписание занятий не найдено."
                send_telegram_message(token, chat_id, err_msg, menu)
                return

            if lang == 'ru':
                res = "<b>📅 Ваше расписание занятий:</b>\n\n"
                for sch in schedules:
                    day_type_str = "Четные дни" if sch.day_type == 'even' else "Нечетные дни"
                    res += (
                        f"📚 <b>{sch.group.name}</b> ({sch.group.course.name if sch.group.course else ''})\n"
                        f"⏰ Время: {sch.start_time.strftime('%H:%M')} - {sch.end_time.strftime('%H:%M')}\n"
                        f"🗓 Дни: {day_type_str}\n"
                        f"🚪 Кабинет: {sch.room_name}\n\n"
                    )
            else:
                res = "<b>📅 Sizning dars jadvalingiz:</b>\n\n"
                for sch in schedules:
                    day_type_str = "Juft kunlar" if sch.day_type == 'even' else "Toq kunlar"
                    res += (
                        f"📚 <b>{sch.group.name}</b> ({sch.group.course.name if sch.group.course else ''})\n"
                        f"⏰ Vaqt: {sch.start_time.strftime('%H:%M')} - {sch.end_time.strftime('%H:%M')}\n"
                        f"🗓 Kunlar: {day_type_str}\n"
                        f"🚪 Xona: {sch.room_name}\n\n"
                    )
            send_telegram_message(token, chat_id, res, menu)

        elif text in ["📋 Mening vazifalarim", "📋 Мои задачи"]:
            from tasks.models import Item
            tasks = Item.objects.filter(assigned_to=user, is_completed=False).order_by('due_date')[:10]
            if not tasks.exists():
                res = "Sizga yuklatilgan faol vazifalar topilmadi." if lang == 'uz' else "Активные задачи не найдены."
            else:
                if lang == 'ru':
                    res = "<b>📋 Ваши активные задачи (до 10 шт):</b>\n\n"
                    for t in tasks:
                        due = t.due_date.strftime("%d.%m.%Y %H:%M") if t.due_date else "Не указан"
                        res += f"📌 <b>{t.title}</b>\n💬 {t.description or '-'}\n📅 Срок: {due}\n\n"
                else:
                    res = "<b>📋 Sizning faol vazifalaringiz (10 tagacha):</b>\n\n"
                    for t in tasks:
                        due = t.due_date.strftime("%d.%m.%Y %H:%M") if t.due_date else "Kiritilmagan"
                        res += f"📌 <b>{t.title}</b>\n💬 {t.description or '-'}\n📅 Muddat: {due}\n\n"
            send_telegram_message(token, chat_id, res, menu)

        elif text in ["💰 Oylik va hisoblar", "💰 Зарплата и расчеты"]:
            from finance.models import Salary, TeacherSalaryCalculation
            salaries = Salary.objects.filter(employee=user).order_by('-date')[:5]
            calcs = TeacherSalaryCalculation.objects.filter(teacher=user).order_by('-created_at')[:5]
            
            if lang == 'ru':
                res = "<b>💰 Зарплата и финансовые расчеты:</b>\n\n"
                res += "💵 <b>Последние выплаты:</b>\n"
                if not salaries.exists():
                    res += "  Выплаты не найдены.\n"
                for s in salaries:
                    status = "Оплачено ✅" if s.status == 'paid' else "В ожидании ⏳"
                    res += f"  • {s.date}: <code>{int(s.amount or 0):,} UZS</code> - {status}\n"
                
                res += "\n📊 <b>Последние расчеты зарплаты:</b>\n"
                if not calcs.exists():
                    res += "  Расчеты не найдены.\n"
                for c in calcs:
                    res += f"  • Период: {c.period}\n    Начислено: <code>{int(c.calculated_amount or 0):,}</code> | Бонус: {int(c.bonus or 0):,} | Штраф: {int(c.penalty or 0):,}\n"
            else:
                res = "<b>💰 Oylik va moliyaviy hisob-kitoblar:</b>\n\n"
                res += "💵 <b>Oxirgi oylik to'lovlari:</b>\n"
                if not salaries.exists():
                    res += "  To'lovlar topilmadi.\n"
                for s in salaries:
                    status = "To'langan ✅" if s.status == 'paid' else "Kutilmoqda ⏳"
                    res += f"  • {s.date}: <code>{int(s.amount or 0):,} UZS</code> - {status}\n"
                
                res += "\n📊 <b>Oxirgi oylik hisob-kitoblari:</b>\n"
                if not calcs.exists():
                    res += "  Hisob-kitoblar topilmadi.\n"
                for c in calcs:
                    res += f"  • Davr: {c.period}\n    Hisoblandi: <code>{int(c.calculated_amount or 0):,}</code> | Bonus: {int(c.bonus or 0):,} | Jarima: {int(c.penalty or 0):,}\n"
            res = res.replace(",", " ")
            send_telegram_message(token, chat_id, res, menu)

        elif text in ["🔔 Bildirishnomalar", "🔔 Уведомления"]:
            from communication.models import Notification
            notifs = Notification.objects.filter(user=user).order_by('-created_at')[:10]
            if not notifs.exists():
                res = "Yangi bildirishnomalar mavjud emas." if lang == 'uz' else "Новые уведомления отсутствуют."
            else:
                if lang == 'ru':
                    res = "<b>🔔 Ваши последние уведомления (до 10 шт):</b>\n\n"
                    for n in notifs:
                        date_str = n.created_at.strftime("%d.%m.%Y %H:%M")
                        res += f"📅 {date_str}\n📌 <b>{n.title}</b>\n💬 {n.message}\n\n"
                else:
                    res = "<b>🔔 Sizning oxirgi bildirishnomalaringiz (10 tagacha):</b>\n\n"
                    for n in notifs:
                        date_str = n.created_at.strftime("%d.%m.%Y %H:%M")
                        res += f"📅 {date_str}\n📌 <b>{n.title}</b>\n💬 {n.message}\n\n"
            send_telegram_message(token, chat_id, res, menu)



        else:
            err_msg = "Noma'lum buyruq. Iltimos menyudan foydalaning." if lang == 'uz' else "Неизвестная команда. Пожалуйста, используйте меню."
            send_telegram_message(token, chat_id, err_msg, menu)
