from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
from decimal import Decimal

from crm.models import Lead
from finance.models import Payment
from academics.models import Attendance
from .models import KPIGoal

def get_active_kpi_subgoal(employee, event_type, date_val):
    if not employee:
        return None
    # Find active goal for this employee covering the event date
    goal = KPIGoal.objects.filter(
        employee=employee,
        start_date__lte=date_val,
        end_date__gte=date_val,
        status='active'
    ).first()
    if goal:
        return goal.sub_goals.filter(system_event=event_type, metric_type='automatic').first()
    return None


# 1. CRM Lead Status Signals (won / lost)
@receiver(post_save, sender=Lead)
def lead_kpi_sync(sender, instance, created, **kwargs):
    try:
        old_status = getattr(instance, '_old_status', None)
        new_status = instance.status
        
        # Determine responsible employee
        employee = instance.moderator or instance.created_by
        if not employee:
            return

        date_val = instance.contacted_at or timezone.now().date()
        if hasattr(date_val, 'date'):
            date_val = date_val.date()

        # Lead converted to student (won)
        if old_status != 'won' and new_status == 'won':
            sub = get_active_kpi_subgoal(employee, 'lead_to_student', date_val)
            if sub:
                sub.current_value = Decimal(str(sub.current_value)) + Decimal('1.00')
                sub.save()
        elif old_status == 'won' and new_status != 'won':
            sub = get_active_kpi_subgoal(employee, 'lead_to_student', date_val)
            if sub:
                sub.current_value = max(Decimal('0.00'), Decimal(str(sub.current_value)) - Decimal('1.00'))
                sub.save()

        # Lead lost (lost)
        if old_status != 'lost' and new_status == 'lost':
            sub = get_active_kpi_subgoal(employee, 'lost_lead', date_val)
            if sub:
                sub.current_value = Decimal(str(sub.current_value)) + Decimal('1.00')
                sub.save()
        elif old_status == 'lost' and new_status != 'lost':
            sub = get_active_kpi_subgoal(employee, 'lost_lead', date_val)
            if sub:
                sub.current_value = max(Decimal('0.00'), Decimal(str(sub.current_value)) - Decimal('1.00'))
                sub.save()

    except Exception as e:
        # Prevent any KPI errors from breaking core transactions
        print(f"Error in lead_kpi_sync: {e}")


# 2. Payment Received Signals
@receiver(pre_save, sender=Payment)
def payment_kpi_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_payment = Payment.objects.get(pk=instance.pk)
            instance._old_amount = old_payment.amount
            instance._old_employee = old_payment.employee
        except Payment.DoesNotExist:
            instance._old_amount = None
            instance._old_employee = None
    else:
        instance._old_amount = None
        instance._old_employee = None


@receiver(post_save, sender=Payment)
def payment_kpi_sync(sender, instance, created, **kwargs):
    try:
        employee = instance.employee
        if not employee:
            return

        date_val = instance.date
        if hasattr(date_val, 'date'):
            date_val = date_val.date()

        if created:
            sub = get_active_kpi_subgoal(employee, 'new_payment', date_val)
            if sub:
                sub.current_value = Decimal(str(sub.current_value)) + Decimal(str(instance.amount))
                sub.save()
        else:
            old_amount = getattr(instance, '_old_amount', None)
            old_employee = getattr(instance, '_old_employee', None)
            if old_amount is not None:
                if old_employee and old_employee != employee:
                    # Subtract from old employee
                    old_sub = get_active_kpi_subgoal(old_employee, 'new_payment', date_val)
                    if old_sub:
                        old_sub.current_value = max(Decimal('0.00'), Decimal(str(old_sub.current_value)) - Decimal(str(old_amount)))
                        old_sub.save()
                    # Add to new employee
                    new_sub = get_active_kpi_subgoal(employee, 'new_payment', date_val)
                    if new_sub:
                        new_sub.current_value = Decimal(str(new_sub.current_value)) + Decimal(str(instance.amount))
                        new_sub.save()
                else:
                    diff = Decimal(str(instance.amount)) - Decimal(str(old_amount))
                    if diff != 0:
                        sub = get_active_kpi_subgoal(employee, 'new_payment', date_val)
                        if sub:
                            sub.current_value = max(Decimal('0.00'), Decimal(str(sub.current_value)) + diff)
                            sub.save()
    except Exception as e:
        print(f"Error in payment_kpi_sync: {e}")


@receiver(post_delete, sender=Payment)
def payment_kpi_delete(sender, instance, **kwargs):
    try:
        employee = instance.employee
        if not employee:
            return

        date_val = instance.date
        if hasattr(date_val, 'date'):
            date_val = date_val.date()

        sub = get_active_kpi_subgoal(employee, 'new_payment', date_val)
        if sub:
            sub.current_value = max(Decimal('0.00'), Decimal(str(sub.current_value)) - Decimal(str(instance.amount)))
            sub.save()
    except Exception as e:
        print(f"Error in payment_kpi_delete: {e}")


# 3. Attendance Signals
@receiver(pre_save, sender=Attendance)
def attendance_kpi_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_att = Attendance.objects.get(pk=instance.pk)
            instance._old_status = old_att.status
        except Attendance.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Attendance)
def attendance_kpi_sync(sender, instance, created, **kwargs):
    try:
        # Determine teacher (employee) to credit
        # Try to resolve teacher from the group
        group = instance.group
        if not group or not group.teacher:
            return
        
        employee = group.teacher

        date_val = instance.date
        if hasattr(date_val, 'date'):
            date_val = date_val.date()

        old_status = getattr(instance, '_old_status', None)
        new_status = instance.status

        # We count present or late as "attendance taken successfully"
        was_present = old_status in ('present', 'late')
        is_present = new_status in ('present', 'late')

        if created and is_present:
            sub = get_active_kpi_subgoal(employee, 'attendance_taken', date_val)
            if sub:
                sub.current_value = Decimal(str(sub.current_value)) + Decimal('1.00')
                sub.save()
        elif not created:
            if not was_present and is_present:
                sub = get_active_kpi_subgoal(employee, 'attendance_taken', date_val)
                if sub:
                    sub.current_value = Decimal(str(sub.current_value)) + Decimal('1.00')
                    sub.save()
            elif was_present and not is_present:
                sub = get_active_kpi_subgoal(employee, 'attendance_taken', date_val)
                if sub:
                    sub.current_value = max(Decimal('0.00'), Decimal(str(sub.current_value)) - Decimal('1.00'))
                    sub.save()
    except Exception as e:
        print(f"Error in attendance_kpi_sync: {e}")


@receiver(post_delete, sender=Attendance)
def attendance_kpi_delete(sender, instance, **kwargs):
    try:
        group = instance.group
        if not group or not group.teacher:
            return
        
        employee = group.teacher

        date_val = instance.date
        if hasattr(date_val, 'date'):
            date_val = date_val.date()

        if instance.status in ('present', 'late'):
            sub = get_active_kpi_subgoal(employee, 'attendance_taken', date_val)
            if sub:
                sub.current_value = max(Decimal('0.00'), Decimal(str(sub.current_value)) - Decimal('1.00'))
                sub.save()
    except Exception as e:
        print(f"Error in attendance_kpi_delete: {e}")
