from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q
from django.utils import timezone
from academics.models import Attendance, Group, GroupLesson,Student
from crm.models import Lead  # Lead modelingiz qaysi appda bo'lsa o'sha yo'lni yozing (masalan: crm.models)
from .serializers import GlobalAttendanceSerializer


class GlobalAttendanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        org_id = getattr(request.user, 'organization_id', None)
        if not org_id:
            return Response({"detail": "Tashkilot aniqlanmadi"}, status=400)

        # Frontenddan (Abdulmajid) kelayotgan filter parametrlari
        date_param = request.query_params.get('date')
        date_from_param = request.query_params.get('date_from')
        date_to_param = request.query_params.get('date_to')

        def normalize_date(d_str):
            if not d_str:
                return None
            import re
            if re.match(r'^\d{2}/\d{2}/\d{4}$', d_str):
                parts = d_str.split('/')
                return f"{parts[2]}-{parts[1]}-{parts[0]}"
            elif re.match(r'^\d{2}-\d{2}-\d{4}$', d_str):
                parts = d_str.split('-')
                return f"{parts[2]}-{parts[1]}-{parts[0]}"
            return d_str

        date_from = normalize_date(date_from_param or date_param)
        date_to = normalize_date(date_to_param)

        attendance_status = request.query_params.get('attendance_status')  # present, absent, excused
        group_id = request.query_params.get('group_id')
        teacher_id = request.query_params.get('teacher_id')
        branch_id = request.query_params.get('branch_id') or request.query_params.get('branch')

        # 🚀 Lead (CRM) bilan bog'liq filterlar
        pipeline_id = request.query_params.get('pipeline_id')  # Ranglar/Bosqichlar filtri (Lead Pipeline)
        lead_status = request.query_params.get('lead_status')  # open, won, lost, first_lesson

        # Davomat uchun asosiy so'rov
        queryset = Attendance.objects.filter(organization_id=org_id)
        if date_from and date_to:
            queryset = queryset.filter(date__range=[date_from, date_to])
        elif date_from:
            queryset = queryset.filter(date=date_from)
        else:
            queryset = queryset.filter(date=timezone.now().date().isoformat())

        queryset = queryset.select_related('student', 'group', 'group__teacher').order_by('-id')

        # Dinamik filtrlash
        if attendance_status:
            status_map = {
                'keldi': 'present',
                'kelmagan': 'absent',
                'sababsiz': 'absent',
                'kechikdi': 'late',
                'sababli': 'excused',
                'present': 'present',
                'absent': 'absent',
                'late': 'late',
                'excused': 'excused'
            }
            mapped_status = status_map.get(attendance_status.lower(), attendance_status)
            queryset = queryset.filter(status=mapped_status)
        if group_id:
            queryset = queryset.filter(group_id=group_id)
        if teacher_id:
            queryset = queryset.filter(group__teacher_id=teacher_id)
        if branch_id:
            queryset = queryset.filter(branch_id=branch_id)

        # 🚀 CRM Lead ma'lumotlari orqali filtrlash (Telefon raqami orqali bog'lanadi)
        if pipeline_id or lead_status:
            # Mos keladigan lidlarning telefon raqamlarini olamiz
            lead_filters = Q(organization_id=org_id)
            if pipeline_id:
                lead_filters &= Q(pipeline_id=pipeline_id)
            if lead_status:
                lead_filters &= Q(status=lead_status)

            matching_phones = Lead.objects.filter(lead_filters).values_list('phone', flat=True)
            # Davomat ro'yxatini faqat shu telefon raqamli o'quvchilarga qisqartiramiz
            queryset = queryset.filter(student__phone__in=matching_phones)

        # Serializer orqali ma'lumotlarni chiqarish
        serializer = GlobalAttendanceSerializer(queryset, many=True)
        return Response(serializer.data)


class AttendanceAnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        org_id = getattr(request.user, 'organization_id', None)
        if not org_id:
            return Response({"detail": "Tashkilot aniqlanmadi"}, status=400)

        date_param = request.query_params.get('date')
        date_from_param = request.query_params.get('date_from')
        date_to_param = request.query_params.get('date_to')

        def normalize_date(d_str):
            if not d_str:
                return None
            import re
            if re.match(r'^\d{2}/\d{2}/\d{4}$', d_str):
                parts = d_str.split('/')
                return f"{parts[2]}-{parts[1]}-{parts[0]}"
            elif re.match(r'^\d{2}-\d{2}-\d{4}$', d_str):
                parts = d_str.split('-')
                return f"{parts[2]}-{parts[1]}-{parts[0]}"
            return d_str

        date_from = normalize_date(date_from_param or date_param)
        date_to = normalize_date(date_to_param)

        attendance_query = Attendance.objects.filter(organization_id=org_id)
        lesson_query = GroupLesson.objects.filter(organization_id=org_id)

        if date_from and date_to:
            attendance_query = attendance_query.filter(date__range=[date_from, date_to])
            lesson_query = lesson_query.filter(date__range=[date_from, date_to])
        elif date_from:
            attendance_query = attendance_query.filter(date=date_from)
            lesson_query = lesson_query.filter(date=date_from)
        else:
            today = timezone.now().date().isoformat()
            attendance_query = attendance_query.filter(date=today)
            lesson_query = lesson_query.filter(date=today)

        # Davomat statistikasi
        stats = attendance_query.aggregate(
            kelganlar=Count('id', filter=Q(status='present')),
            sababli=Count('id', filter=Q(status='excused')),
            sababsiz=Count('id', filter=Q(status='absent')),
        )

        # 🚀 Lead modelidan "Birinchi darsga yozilganlar" sonini hisoblash
        first_lesson_count = Lead.objects.filter(organization_id=org_id, status='first_lesson',
                                                 is_archived=False).count()

        # Davomat qilinmagan guruhlar soni
        davomat_qilinmagan_guruhlar = 0
        for lesson in lesson_query:
            if not Attendance.objects.filter(group=lesson.group, date=lesson.date).exists():
                davomat_qilinmagan_guruhlar += 1

        return Response({
            "summary": {
                "kelganlar": stats['kelganlar'] or 0,
                "sababli": stats['sababli'] or 0,
                "sababsiz": stats['sababsiz'] or 0,
                "birinchi_dars": first_lesson_count,  # Lead modelidan aniq keldi!
                "birinchi dars": first_lesson_count,  # Space version to support all frontend variants
                "muzlatilgan": 0,  # Loyihada talaba statusi qo'shilganda integratsiya qilinadi
                "davomat_qilinmagan": davomat_qilinmagan_guruhlar
            }
        })


class UnmarkedGroupsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        org_id = getattr(request.user, 'organization_id', None)
        if not org_id:
            return Response({"detail": "Tashkilot aniqlanmadi"}, status=400)

        date_param = request.query_params.get('date')
        date_from_param = request.query_params.get('date_from')
        date_to_param = request.query_params.get('date_to')

        def normalize_date(d_str):
            if not d_str:
                return None
            import re
            if re.match(r'^\d{2}/\d{2}/\d{4}$', d_str):
                parts = d_str.split('/')
                return f"{parts[2]}-{parts[1]}-{parts[0]}"
            elif re.match(r'^\d{2}-\d{2}-\d{4}$', d_str):
                parts = d_str.split('-')
                return f"{parts[2]}-{parts[1]}-{parts[0]}"
            return d_str

        date_from = normalize_date(date_from_param or date_param)
        date_to = normalize_date(date_to_param)

        lesson_query = GroupLesson.objects.filter(organization_id=org_id)
        if date_from and date_to:
            lesson_query = lesson_query.filter(date__range=[date_from, date_to])
        elif date_from:
            lesson_query = lesson_query.filter(date=date_from)
        else:
            lesson_query = lesson_query.filter(date=timezone.now().date().isoformat())

        # Bugun kalendarda darsi bor guruhlar
        today_lessons = lesson_query.select_related('group', 'group__teacher')

        unmarked_groups = []
        for lesson in today_lessons:
            if not lesson.group:
                continue
            has_attendance = Attendance.objects.filter(group=lesson.group, date=lesson.date).exists()
            if not has_attendance:
                teacher = lesson.group.teacher
                teacher_name = f"{teacher.first_name or ''} {teacher.last_name or ''}".strip() or teacher.username if teacher else "O'qituvchi yo'q"

                unmarked_groups.append({
                    "group_id": lesson.group.id,
                    "group_name": lesson.group.name,
                    "teacher_name": teacher_name,
                    "date": str(lesson.date)
                })

        return Response(unmarked_groups)


class BranchStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        org_id = getattr(request.user, 'organization_id', None)
        if not org_id:
            return Response({"detail": "Tashkilot aniqlanmadi"}, status=400)

        # 1. CRM Lead modeli statistikasi (Faollar va Arxivlanganlarni hisobga olgan holda)
        leads_stats = Lead.objects.filter(organization_id=org_id).aggregate(
            # Faol buyurtmalar (Arxivda bo'lmagan va lost bo'lmaganlar)
            buyurtma_soni=Count('id', filter=Q(is_archived=False) & ~Q(status='lost')),
            # Birinchi darsga yozilganlar
            birinchi_dars=Count('id', filter=Q(status='first_lesson', is_archived=False)),
            # Buyurtmadan ketganlar (Lost statusidagilar yoki is_archived=True bo'lgan lidlar)
            buyurtmadan_ketgan=Count('id', filter=Q(status='lost') | Q(is_archived=True))
        )

        # 2. Real O'quvchilar (Student) soni
        total_students = Student.objects.filter(organization_id=org_id).count()

        # 3. CRM dagi muvaffaqiyatli yakunlanganlar (Won statusidagi lidlar)
        won_leads_count = Lead.objects.filter(organization_id=org_id, status='won').count()

        # Jami real o'quvchilar soni (Student modelida bo'lsa shuni, bo'lmasa Won lidlarni oladi)
        real_active_count = total_students if total_students > 0 else won_leads_count

        # 4. Qarzdorlar filtri (Student balansi yoki Lead debt_limit orqali)
        student_debtors = Student.objects.filter(organization_id=org_id, balance__lt=0.00).count()
        lead_debtors = Lead.objects.filter(organization_id=org_id, status='won', debt_limit__gt=0.00).count()
        total_debtors = student_debtors if student_debtors > 0 else lead_debtors

        # 5. Aktiv guruhlar soni
        active_groups_count = Group.objects.filter(organization_id=org_id, status='active').count()

        # Qarzdorlik foizini hisoblash
        debt_percentage = 0.0
        if real_active_count > 0:
            debt_percentage = round((total_debtors / real_active_count) * 100, 1)

        # Frontend jadvali uchun moslashtirilgan ma'lumotlar
        branch_report = [{
            "id": org_id,
            "filial": getattr(request.user.organization, 'name', "Asosiy Filial"),
            "buyurtma": leads_stats['buyurtma_soni'] or 0,
            "birinchi_darsga_keladiganlar": leads_stats['birinchi_dars'] or 0,
            "yangi_oquvchi": real_active_count,
            "aktiv_oquvchilar": real_active_count,
            "jami_real_bor": real_active_count,
            "guruh_oquvchilari": real_active_count,
            # "Buyurtmadan ketganlar" qatoriga endi arxiv oynasidagi ma'lumotlar ham qo'shildi!
            "buyurtmadan_ketganlar": leads_stats['buyurtmadan_ketgan'] or 0,
            "yangi_oquvchidan_ketganlar": 0,
            "aktiv_oquvchidan_ketganlar": 0,
            "qarzdorlar": total_debtors,
            "guruh": active_groups_count,
            "birinchi_tolovni_qilganlar": 0,
            "jami_oquvchi": real_active_count,
            "jami_aktiv": real_active_count,
            "qarzdorlarning_aktivga_nisbatan_foizi": f"{debt_percentage}%"
        }]

        return Response(branch_report)


class DBDebugAPIView(APIView):
    permission_classes = []  # Allows public access for debugging convenience

    def get(self, request):
        org_id = getattr(request.user, 'organization_id', None)
        if not org_id:
            from organizations.models import Organization
            first_org = Organization.objects.first()
            if first_org:
                org_id = first_org.id
        from academics.models import Attendance, Student, GroupLesson, Group
        
        attendances_all = Attendance.objects.all()
        students_all = Student.objects.all()
        lessons_all = GroupLesson.objects.all()
        groups_all = Group.objects.all()
        
        attendances_org = Attendance.objects.filter(organization_id=org_id)
        students_org = Student.objects.filter(organization_id=org_id)
        lessons_org = GroupLesson.objects.filter(organization_id=org_id)
        groups_org = Group.objects.filter(organization_id=org_id)
        
        # Convert date to string format for JSON serialization
        sample_attendance_dates = [str(d) for d in attendances_org.values_list('date', flat=True).distinct()[:15]]
        sample_lesson_dates = [str(d) for d in lessons_org.values_list('date', flat=True).distinct()[:15]]
        
        sample_attendance_dates_all = [str(d) for d in attendances_all.values_list('date', flat=True).distinct()[:15]]
        sample_lesson_dates_all = [str(d) for d in lessons_all.values_list('date', flat=True).distinct()[:15]]
        
        from organizations.models import Organization
        organizations = list(Organization.objects.values('id', 'name'))
        
        attendances_details = []
        for att in attendances_all.select_related('student', 'group'):
            attendances_details.append({
                "id": att.id,
                "organization_id": att.organization_id,
                "branch_id": att.branch_id,
                "date": str(att.date),
                "status": att.status,
                "student_id": att.student_id,
                "student_name": f"{att.student.first_name} {att.student.last_name or ''}".strip() if att.student else "None",
                "group_id": att.group_id,
                "group_name": att.group.name if att.group else "None",
            })
            
        groups_details = list(groups_all.values('id', 'organization_id', 'branch_id', 'name'))
        
        return Response({
            "user": {
                "id": request.user.id if request.user.is_authenticated else None,
                "username": request.user.username if request.user.is_authenticated else "Anonymous",
                "role": getattr(request.user, 'role', None) if request.user.is_authenticated else None,
                "organization_id": org_id,
                "branch_id": getattr(request.user, 'branch_id', None) if request.user.is_authenticated else None,
            },
            "organizations": organizations,
            "all_attendances": attendances_details,
            "all_groups": groups_details,
            "database_totals_across_all_organizations": {
                "total_students": students_all.count(),
                "total_groups": groups_all.count(),
                "total_attendances": attendances_all.count(),
                "total_group_lessons": lessons_all.count(),
                "sample_attendance_dates": sample_attendance_dates_all,
                "sample_lesson_dates": sample_lesson_dates_all
            },
            "your_organization_totals": {
                "total_students": students_org.count(),
                "total_groups": groups_org.count(),
                "total_attendances": attendances_org.count(),
                "total_group_lessons": lessons_org.count(),
                "sample_attendance_dates": sample_attendance_dates,
                "sample_lesson_dates": sample_lesson_dates
            }
        })




