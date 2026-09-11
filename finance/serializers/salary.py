import datetime
from decimal import Decimal
from django.db import models
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from finance.models import (
    Salary, TeacherSalaryRule, TeacherSalaryCalculation, StaffSalaryPercent,
    Bonus, Fine
)


class StaffSalaryPercentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffSalaryPercent
        fields = '__all__'
        read_only_fields = ('organization', 'branch', 'created_at', 'updated_at')


class SalarySerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)

    class Meta:
        model = Salary
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')


class TeacherSalaryRuleSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.get_full_name', default='Standart', read_only=True)

    class Meta:
        model = TeacherSalaryRule
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        percent_per_student = data.get('percent_per_student')
        fixed_bonus = data.get('fixed_bonus')
        
        try:
            val_pct = float(percent_per_student) if percent_per_student is not None else 0
            val_fix = float(fixed_bonus) if fixed_bonus is not None else 0
        except ValueError:
            val_pct = 0
            val_fix = 0
            
        if val_pct > 0:
            data['rule_type'] = 'percentage'
            data['rate'] = val_pct
        elif val_fix > 0:
            data['rule_type'] = 'fixed'
            data['rate'] = val_fix
        else:
            if 'rule_type' not in data:
                data['rule_type'] = 'fixed'
            if 'rate' not in data:
                data['rate'] = 0.0
                
        if 'period' not in data or not data['period']:
            effective_from = data.get('effective_from')
            if effective_from:
                try:
                    parts = effective_from.split('-')
                    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit() or len(parts[0]) != 4 or len(parts[1]) != 2:
                        raise ValueError()
                    data['period'] = f"{parts[0]}-{parts[1]}"
                except Exception:
                    raise serializers.ValidationError({"effective_from": "Sana formati noto'g'ri (YYYY-MM-DD bo'lishi kerak)."})
            else:
                data['period'] = datetime.date.today().strftime('%Y-%m')
                
        return super().to_internal_value(data)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        is_percentage = instance.rule_type == 'percentage'
        
        rep['percent_per_student'] = float(instance.rate) if is_percentage else 0.0
        rep['fixed_bonus'] = float(instance.rate) if not is_percentage else 0.0
        rep['effective_from'] = instance.created_at.date().isoformat() if instance.created_at else None
        rep['effective_to'] = None
        return rep


class TeacherSalaryCalculationSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.get_full_name', read_only=True)
    bonus = serializers.SerializerMethodField()
    penalty = serializers.SerializerMethodField()
    advance = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    net_salary = serializers.SerializerMethodField()

    class Meta:
        model = TeacherSalaryCalculation
        fields = '__all__'
        read_only_fields = ('organization', 'created_at', 'updated_at')

    @extend_schema_field(serializers.FloatField)
    def get_bonus(self, obj):
        if hasattr(obj, '_cached_bonus'):
            return obj._cached_bonus
        if not obj.teacher_id or not obj.period:
            return 0.0
        try:
            year, month = map(int, obj.period.split('-'))
            val = Bonus.objects.filter(
                organization_id=obj.organization_id,
                employee_id=obj.teacher_id,
                date__year=year,
                date__month=month
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            obj._cached_bonus = float(val)
            return obj._cached_bonus
        except Exception:
            return 0.0

    @extend_schema_field(serializers.FloatField)
    def get_penalty(self, obj):
        if hasattr(obj, '_cached_penalty'):
            return obj._cached_penalty
        if not obj.teacher_id or not obj.period:
            return 0.0
        try:
            year, month = map(int, obj.period.split('-'))
            val = Fine.objects.filter(
                organization_id=obj.organization_id,
                employee_id=obj.teacher_id,
                date__year=year,
                date__month=month
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            obj._cached_penalty = float(val)
            return obj._cached_penalty
        except Exception:
            return 0.0

    @extend_schema_field(serializers.FloatField)
    def get_advance(self, obj):
        if hasattr(obj, '_cached_advance'):
            return obj._cached_advance
        if not obj.teacher_id or not obj.period:
            return 0.0
        try:
            year, month = map(int, obj.period.split('-'))
            from finance.models import Transaction
            val = Transaction.objects.filter(
                organization_id=obj.organization_id,
                employee_id=obj.teacher_id,
                type='EXPENSE',
                category='ADVANCE',
                created_at__year=year,
                created_at__month=month
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            obj._cached_advance = float(val)
            return obj._cached_advance
        except Exception:
            return 0.0

    @extend_schema_field(serializers.FloatField)
    def get_paid_amount(self, obj):
        if hasattr(obj, '_cached_paid_amount'):
            return obj._cached_paid_amount
        if not obj.teacher_id or not obj.period:
            return 0.0
        try:
            year, month = map(int, obj.period.split('-'))
            from academics.models import TeacherSalaryPayment
            from django.db.models import Q
            val = TeacherSalaryPayment.objects.filter(
                Q(organization_id=obj.organization_id, teacher_id=obj.teacher_id) &
                (Q(period=obj.period) | Q(paid_at__year=year, paid_at__month=month))
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            obj._cached_paid_amount = float(val)
            return obj._cached_paid_amount
        except Exception:
            return 0.0

    @extend_schema_field(serializers.FloatField)
    def get_net_salary(self, obj):
        calc = float(obj.calculated_amount or 0)
        bonus = self.get_bonus(obj)
        penalty = self.get_penalty(obj)
        advance = self.get_advance(obj)
        paid = self.get_paid_amount(obj)
        net = max(0.0, (calc + bonus) - (paid + advance + penalty))
        return round(net, 2)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        bonus = self.get_bonus(instance)
        penalty = self.get_penalty(instance)
        advance = self.get_advance(instance)
        paid_amount = self.get_paid_amount(instance)

        details = instance.details or {}
        rule_type = details.get('rule_type')
        if not rule_type:
            if instance.teacher and instance.teacher.salary_percentage:
                rule_type = 'percentage'
            else:
                rule_type = 'fixed'

        att_charges = details.get('attendance_charges', {})
        davomat_count = details.get('davomat_count') or details.get('attendance_count') or len(att_charges)
        lessons_count = details.get('lessons_count') or details.get('lesson_count') or 0
        davomat_summa = float(details.get('davomat_summa', 0.0))

        if att_charges and davomat_summa == 0.0:
            try:
                davomat_summa = float(sum(Decimal(str(v)) for v in att_charges.values()))
            except Exception:
                davomat_summa = 0.0

        if (davomat_count == 0 or lessons_count == 0 or (rule_type == 'percentage' and davomat_summa == 0.0)) and instance.teacher_id and instance.period:
            try:
                year, month = map(int, instance.period.split('-'))
                from academics.models import Attendance
                atts_qs = Attendance.objects.filter(
                    group__teacher_id=instance.teacher_id,
                    organization_id=instance.organization_id,
                    date__year=year,
                    date__month=month
                )
                if davomat_count == 0:
                    davomat_count = atts_qs.filter(status__in=['present', 'late']).count()
                if lessons_count == 0:
                    lessons_count = atts_qs.values('group_id', 'date').distinct().count()

                if rule_type == 'percentage' and davomat_summa == 0.0:
                    from finance.models import Transaction
                    rate_str = details.get('rate') or (str(instance.teacher.salary_percentage.percent) if instance.teacher and instance.teacher.salary_percentage else '50')
                    rate = Decimal(rate_str)
                    atts_present = atts_qs.filter(status__in=['present', 'late'])
                    att_ids = list(atts_present.values_list('id', flat=True))
                    if att_ids:
                        tx_sum = Transaction.objects.filter(
                            organization_id=instance.organization_id,
                            description__startswith='Davomat #'
                        ).filter(
                            description__in=[f"Davomat #{aid}:" for aid in att_ids]
                        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
                        if tx_sum > 0:
                            davomat_summa = float(round(tx_sum * (rate / Decimal('100.00')), 2))
                        else:
                            from academics.models import StudentGroup
                            sg_prices = dict(StudentGroup.objects.filter(group__teacher_id=instance.teacher_id, organization_id=instance.organization_id).values_list('student_id', 'price'))
                            tot_share = Decimal('0.00')
                            for a in atts_present.select_related('group__course'):
                                p = sg_prices.get(a.student_id) or (a.group.course.price if a.group and a.group.course else Decimal('0.00'))
                                if p:
                                    tot_share += round((p / Decimal('12.00')) * (rate / Decimal('100.00')), 2)
                            davomat_summa = float(tot_share)
            except Exception:
                pass

        if rule_type == 'percentage':
            total_earned = davomat_summa
        else:
            calc_val = float(instance.calculated_amount or 0)
            total_earned = calc_val

        net = max(0.0, (total_earned + bonus) - (paid_amount + advance + penalty))

        teacher_obj = instance.teacher
        t_first = teacher_obj.first_name if teacher_obj else ''
        t_last = teacher_obj.last_name if teacher_obj else ''
        t_full = f"{t_first} {t_last}".strip() or "Noma'lum"
        t_phone = getattr(teacher_obj, 'phone_number', None) or getattr(teacher_obj, 'phone', '') if teacher_obj else ''

        rep['teacher_name'] = t_full
        rep['full_name'] = t_full
        rep['first_name'] = t_first
        rep['last_name'] = t_last
        rep['phone_number'] = t_phone or ''
        rep['phone'] = t_phone or ''
        rep['telefon'] = t_phone or ''

        rep['calculated_amount'] = round(net, 2)
        rep['amount'] = round(net, 2)
        rep['ish_haqi'] = round(net, 2)
        rep['salary'] = round(net, 2)

        rep['davomat'] = davomat_count
        rep['davomat_count'] = davomat_count
        rep['attendances_count'] = davomat_count
        rep['att_count'] = davomat_count
        rep['lessons_count'] = lessons_count

        rep['davomatdan'] = round(davomat_summa, 2)
        rep['davomatdan_ushlangani'] = round(davomat_summa, 2)
        rep['davomat_summa'] = round(davomat_summa, 2)
        rep['attendance_salary'] = round(davomat_summa, 2)
        rep['attendance_amount'] = round(davomat_summa, 2)
        rep['gross_davomatdan'] = round(davomat_summa, 2)

        rep['bonus'] = bonus
        rep['penalty'] = penalty
        rep['jarima'] = penalty
        rep['advance'] = advance
        rep['avans'] = advance

        is_paid = (paid_amount >= (total_earned + bonus - advance - penalty)) if (total_earned > 0) else False

        rep['paid_amount'] = round(paid_amount, 2)
        rep['to_langan'] = round(paid_amount, 2)
        rep['aklad'] = round(total_earned, 2)
        rep['akladi'] = round(total_earned, 2)
        rep['base_salary'] = round(total_earned, 2)
        rep['total_earned'] = round(total_earned, 2)
        rep['net_salary'] = round(net, 2)
        rep['final_payout'] = round(net, 2)
        rep['to_lanmagan'] = round(net, 2)
        rep['to_lanmagan_str'] = f"{int(net):,} UZS".replace(",", " ")
        rep['remaining_balance'] = round(net, 2)
        rep['is_paid'] = is_paid
        rep['status'] = 'paid' if is_paid else 'unpaid'
        return rep
