import datetime
from decimal import Decimal
from django.db.models import Sum, Q, Count
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import HasOrganizationPagePermission
from organizations.models import Branch
from accounts.models import User
from academics.models import (
    Student, StudentGroup, StudentGroupLeave, Room, GroupLesson, Attendance, TeacherSalaryPayment
)
from finance.models import Payment, Expense, Salary
from .base import get_active_branch_id


@extend_schema(
    tags=['Finance - Analytics'],
    summary="Kompaniya sof foydasi grafigi (Oylik dinamika)",
    description="Oxirgi 6 oy bo'yicha kirim, chiqim va to'langan maoshlar asosida sof foyda grafigi ma'lumotlarini qaytaradi.",
    responses={200: OpenApiTypes.OBJECT}
)
class CompanyProfitChartView(TenantViewSetMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, HasOrganizationPagePermission]
    permission_page_name = 'Moliya'

    def get(self, request):
        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        branch_id = self.get_branch_id()
        today = datetime.date.today()
        months = []
        for i in range(5, -1, -1):
            month_offset = today.month - i
            year_offset = today.year
            while month_offset <= 0:
                month_offset += 12
                year_offset -= 1
            months.append((year_offset, month_offset))

        labels = []
        values = []
        uz_months = {
            1: "Yan", 2: "Fev", 3: "Mar", 4: "Apr", 5: "May", 6: "Iyun",
            7: "Iyul", 8: "Avg", 9: "Sen", 10: "Okt", 11: "Nov", 12: "Dek"
        }

        for year, month in months:
            p_filter = {'organization_id': org_id, 'date__year': year, 'date__month': month}
            e_filter = {'organization_id': org_id, 'date__year': year, 'date__month': month}
            s_filter = {'organization_id': org_id, 'date__year': year, 'date__month': month, 'status': 'paid'}
            t_filter = {'organization_id': org_id, 'paid_at__year': year, 'paid_at__month': month}

            if branch_id:
                p_filter['branch_id'] = branch_id
                e_filter['branch_id'] = branch_id
                s_filter['branch_id'] = branch_id
                t_filter['branch_id'] = branch_id

            total_income = Payment.objects.filter(**p_filter).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            total_expense = Expense.objects.filter(**e_filter).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            total_salary = Salary.objects.filter(**s_filter).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            total_teacher_salary = TeacherSalaryPayment.objects.filter(**t_filter).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

            net_profit = total_income - (total_expense + total_salary + total_teacher_salary)

            year_short = str(year)[2:]
            label = f"{uz_months[month]} {year_short}"
            labels.append(label)
            values.append(float(net_profit))

        return Response({
            "labels": labels,
            "values": values
        }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Finance - Analytics'],
    summary="O'qituvchilar samaradorligi hisoboti",
    description="O'qituvchilar kesimida davr bo'yicha talabalar oqimi (faol, ketgan, bitirgan) va o'zgarishlar dinamikasi.",
    parameters=[
        OpenApiParameter('from_date', OpenApiTypes.DATE, description="Boshlanish sanasi"),
        OpenApiParameter('to_date', OpenApiTypes.DATE, description="Tugash sanasi"),
    ],
    responses={200: OpenApiTypes.OBJECT}
)
class TeacherEfficiencyReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        org_id = request.user.organization_id
        branch_id = get_active_branch_id(request)
        from_date_str = request.query_params.get('from_date')
        to_date_str = request.query_params.get('to_date')

        from_date = parse_date(from_date_str) if from_date_str else None
        to_date = parse_date(to_date_str) if to_date_str else timezone.now().date()

        teachers = User.objects.filter(organization_id=org_id, role='teacher')
        if branch_id:
            teachers = teachers.filter(branch_id=branch_id)

        report = []
        for index, teacher in enumerate(teachers, 1):
            group_ids = list(teacher.teaching_groups.values_list('id', flat=True))

            sg_qs = StudentGroup.objects.filter(group_id__in=group_ids)
            sl_qs = StudentGroupLeave.objects.filter(group_id__in=group_ids)

            if from_date:
                start_active = sg_qs.filter(joined_at__date__lt=from_date).count()
                start_left = sl_qs.filter(leave_date__lt=from_date).count()
            else:
                start_active = 0
                start_left = 0

            change_sg = sg_qs
            change_sl = sl_qs
            if from_date:
                change_sg = change_sg.filter(joined_at__date__gte=from_date)
                change_sl = change_sl.filter(leave_date__gte=from_date)
            if to_date:
                change_sg = change_sg.filter(joined_at__date__lte=to_date)
                change_sl = change_sl.filter(leave_date__lte=to_date)

            change_active = change_sg.count()
            change_left = change_sl.count()

            end_sg = sg_qs
            end_sl = sl_qs
            if to_date:
                end_sg = end_sg.filter(joined_at__date__lte=to_date)
                end_sl = end_sl.filter(leave_date__lte=to_date)

            end_active = end_sg.count()
            end_left = end_sl.count()

            name = f"{teacher.first_name} {teacher.last_name or ''}".strip() or teacher.username

            report.append({
                "id": index,
                "teacher_name": name,
                "start_status": {"active": start_active, "left": start_left, "finished": 0, "frozen": 0},
                "changes": {"active": change_active, "left": change_left, "finished": 0, "frozen": 0},
                "end_status": {"active": end_active, "left": end_left, "finished": 0, "frozen": 0}
            })

        return Response(report)


@extend_schema(
    tags=['Finance - Analytics'],
    summary="Administratorlar / Moderatorlar samaradorligi hisoboti",
    description="Administratorlarga biriktirilgan talabalar soni, ketganlar va o'zgarishlar statistikasi.",
    parameters=[
        OpenApiParameter('from_date', OpenApiTypes.DATE, description="Boshlanish sanasi"),
        OpenApiParameter('to_date', OpenApiTypes.DATE, description="Tugash sanasi"),
    ],
    responses={200: OpenApiTypes.OBJECT}
)
class AdministratorEfficiencyReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from_date_str = request.query_params.get('from_date')
        to_date_str = request.query_params.get('to_date')

        from_date = parse_date(from_date_str) if from_date_str else None
        to_date = parse_date(to_date_str) if to_date_str else timezone.now().date()

        org_id = request.user.organization_id
        branch_id = get_active_branch_id(request)
        admins = User.objects.filter(organization_id=org_id, is_staff=True)
        if branch_id:
            admins = admins.filter(branch_id=branch_id)

        report = []
        for index, admin in enumerate(admins, 1):
            students_qs = Student.objects.filter(organization_id=org_id, moderator=admin.id)
            leaves_qs = StudentGroupLeave.objects.filter(organization_id=org_id, student__moderator=admin.id)
            if branch_id:
                students_qs = students_qs.filter(branch_id=branch_id)
                leaves_qs = leaves_qs.filter(branch_id=branch_id)

            if from_date:
                start_active = students_qs.filter(created_at__date__lt=from_date, student_groups__isnull=False).distinct().count()
                start_left = leaves_qs.filter(leave_date__lt=from_date).count()
            else:
                start_active = 0
                start_left = 0

            change_active_qs = students_qs.filter(student_groups__isnull=False)
            change_left_qs = leaves_qs
            if from_date:
                change_active_qs = change_active_qs.filter(created_at__date__gte=from_date)
                change_left_qs = change_left_qs.filter(leave_date__gte=from_date)
            if to_date:
                change_active_qs = change_active_qs.filter(created_at__date__lte=to_date)
                change_left_qs = change_left_qs.filter(leave_date__lte=to_date)

            change_active = change_active_qs.distinct().count()
            change_left = change_left_qs.count()

            end_active_qs = students_qs.filter(student_groups__isnull=False)
            end_left_qs = leaves_qs
            if to_date:
                end_active_qs = end_active_qs.filter(created_at__date__lte=to_date)
                end_left_qs = end_left_qs.filter(leave_date__lte=to_date)

            end_active = end_active_qs.distinct().count()
            end_left = end_left_qs.count()

            report.append({
                "id": index,
                "admin_name": f"{admin.first_name} {admin.last_name}".strip() or admin.username,
                "start_status": {"active": start_active, "left": start_left, "finished": 0, "frozen": 0},
                "changes": {"active": change_active, "left": change_left, "finished": 0, "frozen": 0},
                "end_status": {"active": end_active, "left": end_left, "finished": 0, "frozen": 0}
            })

        return Response(report)


@extend_schema(
    tags=['Finance - Analytics'],
    summary="O'quvchilar ketish sabablari tahlili",
    description="Guruh yoki kursni tark etgan o'quvchilarning ketish sabablari statistikasi va ro'yxati.",
    parameters=[
        OpenApiParameter('from_date', OpenApiTypes.DATE, description="Boshlanish sanasi"),
        OpenApiParameter('to_date', OpenApiTypes.DATE, description="Tugash sanasi"),
    ],
    responses={200: OpenApiTypes.OBJECT}
)
class StudentLeaversReasonsReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from_date_str = request.query_params.get('from_date')
        to_date_str = request.query_params.get('to_date')

        from_date = parse_date(from_date_str) if from_date_str else None
        to_date = parse_date(to_date_str) if to_date_str else None

        org = request.user.organization
        branch_id = get_active_branch_id(request)
        filters = Q(organization=org) | Q(student__organization=org)
        if branch_id:
            filters &= (Q(branch_id=branch_id) | Q(branch_id__isnull=True))

        if from_date:
            filters &= (Q(leave_date__gte=from_date) | Q(created_at__date__gte=from_date))
        if to_date:
            filters &= (Q(leave_date__lte=to_date) | Q(created_at__date__lte=to_date))

        leaves_qs = StudentGroupLeave.objects.filter(filters).select_related(
            'student', 'group', 'leave_reason'
        ).order_by('-leave_date', '-id')

        all_students = []
        reason_groups = {}

        for leave in leaves_qs:
            student_name = ""
            if leave.student:
                first = leave.student.first_name or ""
                last = leave.student.last_name or ""
                student_name = f"{first} {last}".strip()
            if not student_name:
                student_name = leave.student_name or "Noma'lum talaba"

            phone = leave.student.phone if (leave.student and leave.student.phone) else (leave.student_phone or "")
            reason_name = leave.leave_reason.reason if leave.leave_reason else "Sababi ko'rsatilmagan"
            group_name = leave.group.name if leave.group else ""
            leave_dt_str = leave.leave_date.isoformat() if leave.leave_date else (leave.created_at.date().isoformat() if leave.created_at else None)

            item = {
                "id": leave.id,
                "student_id": leave.student_id,
                "student_name": student_name,
                "name": student_name,
                "phone": phone,
                "group_name": group_name,
                "group": group_name,
                "leave_reason": reason_name,
                "reason_name": reason_name,
                "leave_date": leave_dt_str,
                "sana": leave_dt_str,
                "comment": leave.comment or "",
                "refound_amount": float(leave.refound_amount or 0)
            }

            all_students.append(item)
            if reason_name not in reason_groups:
                reason_groups[reason_name] = []
            reason_groups[reason_name].append(item)

        chart_data = []
        table_data = []

        for i, (r_name, r_students) in enumerate(reason_groups.items(), 1):
            count = len(r_students)
            chart_data.append({"reason_name": r_name, "count": count})
            table_data.append({
                "id": i,
                "reason_name": r_name,
                "student_count": count,
                "count": count,
                "students": r_students
            })

        if not chart_data:
            chart_data = [{"reason_name": "Boshqa sabab", "count": 0}]
            table_data = [{"id": 1, "reason_name": "Boshqa sabab", "student_count": 0, "count": 0, "students": []}]

        return Response({
            "total_leavers": len(all_students),
            "chart_data": chart_data,
            "table_data": table_data,
            "students": all_students,
            "leavers": all_students
        })


@extend_schema(
    tags=['Finance - Analytics'],
    summary="Xonalar bandligi va yuklamasi tahlili",
    description="Xonalarda ochilgan faol guruhlar soni va bandlik darajasi hisoboti.",
    parameters=[
        OpenApiParameter('from_date', OpenApiTypes.DATE, description="Boshlanish sanasi"),
        OpenApiParameter('to_date', OpenApiTypes.DATE, description="Tugash sanasi"),
    ],
    responses={200: OpenApiTypes.OBJECT}
)
class RoomAnalyticsReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        org_id = request.user.organization_id
        branch_id = get_active_branch_id(request)

        from_date_str = request.query_params.get('from_date')
        to_date_str = request.query_params.get('to_date')

        from_date = parse_date(from_date_str) if from_date_str else None
        to_date = parse_date(to_date_str) if to_date_str else None

        group_filter = Q()
        if from_date:
            group_filter &= Q(groups__created_at__gte=from_date)
        if to_date:
            group_filter &= Q(groups__created_at__lte=to_date)

        rooms_qs = Room.objects.filter(organization_id=org_id)
        if branch_id:
            rooms_qs = rooms_qs.filter(branch_id=branch_id)

        rooms = rooms_qs.annotate(
            active_groups=Count('groups', filter=group_filter & Q(groups__status='active'))
        )

        chart_data = []
        table_data = []
        for index, room in enumerate(rooms, 1):
            chart_data.append({"room_name": room.name, "count": room.active_groups})
            table_data.append({"id": index, "room_name": room.name, "group_count": room.active_groups})

        return Response({
            "chart_data": chart_data,
            "table_data": table_data
        })


@extend_schema(
    tags=['Finance - Analytics'],
    summary="Filiallar monitoringi va tahlili hisoboti",
    description="Filiallar kesimida lidlar, yangi talabalar, faol o'quvchilar va qarzdorlik ko'rsatkichlari solishtirmasi.",
    parameters=[
        OpenApiParameter('date', OpenApiTypes.DATE, description="Tanlangan sana (YYYY-MM-DD)"),
    ],
    responses={200: OpenApiTypes.OBJECT}
)
class BranchMonitoringReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from crm.models import Lead

        org_id = request.user.organization_id
        date_str = request.query_params.get('date')
        target_date = parse_date(date_str) if date_str else None

        branches = Branch.objects.filter(organization_id=org_id)
        table_data = []

        for index, branch in enumerate(branches, 1):
            leads_qs = Lead.objects.filter(organization_id=org_id, branch=branch, is_archived=False)
            students_qs = Student.objects.filter(organization_id=org_id, branch=branch)

            if target_date:
                leads_qs = leads_qs.filter(created_at__date=target_date)
                students_qs = students_qs.filter(created_at__date=target_date)

            orders = leads_qs.filter(status='open').count()
            first_lesson = leads_qs.filter(status='first_lesson').count()
            new_students = students_qs.count()
            active_students = students_qs.count()
            group_students = students_qs.filter(student_groups__isnull=False).distinct().count()
            order_leavers = leads_qs.filter(status='lost').count()
            debtors = students_qs.filter(balance__lt=0).count()

            debt_percentage = 0
            if active_students > 0:
                debt_percentage = round((debtors / active_students) * 100, 1)

            table_data.append({
                "id": index,
                "branch_name": branch.name,
                "buyurtma": orders,
                "birinchi_dars": first_lesson,
                "yangi_oquvchi": new_students,
                "aktiv_oquvchilar": active_students,
                "guruh_oquvchilari": group_students,
                "buyurtmadan_ketganlar": order_leavers,
                "qarzdorlar": debtors,
                "qarzdorlar_foizi": f"{debt_percentage}%"
            })

        return Response({"table_data": table_data})


@extend_schema(
    tags=['Finance - Analytics'],
    summary="Kiritilmagan davomatlar hisoboti",
    description="O'tkazilgan, lekin davomati belgilanmagan guruh darslari va ulardan yuzaga kelgan yo'qotishlar.",
    parameters=[
        OpenApiParameter('from_date', OpenApiTypes.DATE, description="Boshlanish sanasi"),
        OpenApiParameter('to_date', OpenApiTypes.DATE, description="Tugash sanasi"),
    ],
    responses={200: OpenApiTypes.OBJECT}
)
class UnsubmittedAttendanceReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        org_id = request.user.organization_id
        branch_id = get_active_branch_id(request)

        from_date_str = request.query_params.get('from_date')
        to_date_str = request.query_params.get('to_date')

        from_date = parse_date(from_date_str) if from_date_str else None
        to_date = parse_date(to_date_str) if to_date_str else None

        lesson_filter = Q(organization_id=org_id, is_canceled=False)
        if branch_id:
            lesson_filter &= Q(branch_id=branch_id)
        if from_date:
            lesson_filter &= Q(date__gte=from_date)
        if to_date:
            lesson_filter &= Q(date__lte=to_date)

        all_lessons = GroupLesson.objects.filter(lesson_filter).select_related(
            'group', 'group__teacher', 'group__course'
        ).order_by('date')

        submitted_pairs = set(
            Attendance.objects.filter(organization_id=org_id).values_list('group_id', 'date')
        )

        table_data = []
        total_lost_sum = 0
        seen_groups = set()
        index = 1

        for lesson in all_lessons:
            group = lesson.group
            if not group or (group.id, lesson.date) in submitted_pairs:
                continue

            if group.id in seen_groups:
                continue
            seen_groups.add(group.id)

            group_price = getattr(group, 'price', None) or (
                group.course.price if group.course and hasattr(group.course, 'price') else 300000
            )
            total_lost_sum += float(group_price)

            teacher_name = "O'qituvchi biriktirilmagan"
            if group.teacher:
                teacher_name = f"{group.teacher.first_name} {group.teacher.last_name or ''}".strip() or group.teacher.username

            try:
                lesson_date = lesson.date.strftime("%d.%m.%Y")
            except AttributeError:
                lesson_date = str(lesson.date)

            table_data.append({
                "id": index,
                "group_name": group.name,
                "sana": lesson_date,
                "teacher_name": teacher_name,
                "amount": float(group_price)
            })
            index += 1

        return Response({
            "total_sum": total_lost_sum,
            "currency": "UZS",
            "table_data": table_data
        }, status=200)
