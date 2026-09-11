import csv
import datetime
from io import BytesIO

from academics.models import Student
from academics.serializers import StudentSerializer

DEFAULT_STUDENT_FIELD_MAPPING = {
    'first_name': ['ism', 'first name', 'name', 'first_name'],
    'last_name': ['familiya', 'last name', 'surname', 'last_name'],
    'phone': ['telefon', 'phone', 'phone number', 'phone_number'],
    'email': ['email', 'e-mail'],
    'birth_date': ['tug\'ilgan sana', 'birth date', 'birthday', 'birth_date', 'tugilgan sana'],
    'gender': ['jins', 'gender', 'sex'],
    'balance': ['balans', 'balance'],
    'father_name': ['ota ismi', 'father name', 'father_name'],
    'father_phone': ['ota telefoni', 'father phone', 'father_phone'],
    'mother_name': ['ona ismi', 'mother name', 'mother_name'],
    'mother_phone': ['ona telefoni', 'mother phone', 'mother_phone'],
    'telegram_chat_id': ['telegram', 'telegram chat id', 'telegram_chat_id']
}


def parse_student_import_file(file_obj):
    """
    CSV yoki Excel (.xlsx, .xls) fayllaridan ma'lumotlarni qatorlar (dict) ro'yxati sifatida o'qiydi.
    """
    filename = getattr(file_obj, 'name', '').lower()
    rows_data = []

    if filename.endswith('.csv'):
        try:
            content = file_obj.read()
            if isinstance(content, bytes):
                decoded_file = content.decode('utf-8-sig').splitlines()
            else:
                decoded_file = str(content).splitlines()
            reader = csv.DictReader(decoded_file)
            for row in reader:
                cleaned_row = {k.strip().lower() if k else '': v.strip() if v else '' for k, v in row.items()}
                rows_data.append(cleaned_row)
        except Exception as e:
            raise ValueError(f"CSV faylni o'qishda xatolik: {str(e)}")

    elif filename.endswith(('.xlsx', '.xls')):
        try:
            import openpyxl
            content = file_obj.read()
            wb = openpyxl.load_workbook(filename=BytesIO(content), data_only=True)
            sheet = wb.active

            headers = []
            for cell in sheet[1]:
                if cell.value is not None:
                    headers.append(str(cell.value).strip().lower())
                else:
                    headers.append('')

            for r in range(2, sheet.max_row + 1):
                row_data = {}
                has_data = False
                for c, header in enumerate(headers):
                    if not header:
                        continue
                    val = sheet.cell(row=r, column=c + 1).value
                    if val is not None:
                        has_data = True
                        row_data[header] = str(val).strip()
                    else:
                        row_data[header] = ''
                if has_data:
                    rows_data.append(row_data)
        except Exception as e:
            raise ValueError(f"Excel faylni o'qishda xatolik: {str(e)}")
    else:
        raise ValueError("Faqat .xlsx, .xls yoki .csv fayllar qo'llab-quvvatlanadi.")

    return rows_data


def normalize_student_row(row, field_mapping=None):
    """
    Qatordagi sinonim sarlavhalarni standart maydon nomlariga o'tkazadi.
    """
    mapping = field_mapping or DEFAULT_STUDENT_FIELD_MAPPING
    student_data = {}

    for field, synonyms in mapping.items():
        found_val = None
        for synonym in synonyms:
            if synonym in row and row[synonym]:
                found_val = row[synonym]
                break
        if found_val:
            student_data[field] = found_val

    return student_data


def sanitize_student_data(student_data, org_id, branch_id=None):
    """
    Telefon, tug'ilgan sana va boshlang'ich parollarni tozalab formatlaydi.
    """
    sanitized = dict(student_data)
    sanitized['organization'] = org_id
    if branch_id:
        sanitized['branch'] = branch_id

    phone = sanitized.get('phone')
    if phone:
        phone_digits = ''.join(c for c in str(phone) if c.isdigit())
        if phone_digits:
            sanitized['phone'] = '+' + phone_digits if not str(phone).startswith('+') else '+' + phone_digits

    birth_date = sanitized.get('birth_date')
    if birth_date:
        parsed_date = None
        for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
            try:
                parsed_date = datetime.datetime.strptime(str(birth_date), fmt).date()
                break
            except ValueError:
                pass
        if parsed_date:
            sanitized['birth_date'] = parsed_date.isoformat()
        else:
            sanitized.pop('birth_date', None)

    return sanitized


def import_students_from_file(file_obj, org_id, branch_id=None):
    """
    Fayldan o'quvchilarni import qiladi yoki mavjudlarini yangilaydi.
    """
    rows_data = parse_student_import_file(file_obj)

    success_count = 0
    error_logs = []

    for idx, row in enumerate(rows_data):
        row_num = idx + 2
        normalized = normalize_student_row(row)

        first_name = normalized.get('first_name')
        if not first_name:
            error_logs.append(f"{row_num}-qatorda 'Ism' (first_name) ustuni bo'sh yoki topilmadi.")
            continue

        student_data = sanitize_student_data(normalized, org_id=org_id, branch_id=branch_id)
        phone = student_data.get('phone')

        existing_student = None
        if phone:
            existing_student = Student.objects.filter(phone=phone, organization_id=org_id).first()

        if not existing_student and 'password' not in student_data:
            if phone:
                raw_phone = ''.join(c for c in phone if c.isdigit())
                if len(raw_phone) >= 6:
                    student_data['password'] = raw_phone
                else:
                    student_data['password'] = "smarttalim123"
            else:
                student_data['password'] = "smarttalim123"

        try:
            if existing_student:
                serializer = StudentSerializer(existing_student, data=student_data, partial=True)
            else:
                serializer = StudentSerializer(data=student_data)

            if serializer.is_valid():
                serializer.save(organization_id=org_id, branch_id=branch_id)
                success_count += 1
            else:
                errors_str = ", ".join([f"{k}: {v[0]}" for k, v in serializer.errors.items()])
                error_logs.append(f"{row_num}-qatorda xatolik: {errors_str}")
        except Exception as e:
            error_logs.append(f"{row_num}-qatorda kutilmagan xatolik: {str(e)}")

    return success_count, error_logs
