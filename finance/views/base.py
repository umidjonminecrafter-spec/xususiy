from decimal import Decimal
from django.db.models import Sum


def get_active_branch_id(request):
    branch_id = request.query_params.get('branch') or request.query_params.get('branch_id')
    if branch_id:
        return branch_id
    branch_id = request.META.get('HTTP_X_BRANCH_ID') or request.headers.get('x-branch-id')
    if branch_id:
        return branch_id
    if request.user and request.user.is_authenticated:
        return getattr(request.user, 'branch_id', None)
    return None


def sync_cashbox_balance(cashbox):
    if not cashbox:
        return Decimal('0.00')
    from finance.models import Transaction, Cashbox

    income = Transaction.objects.filter(
        cashbox=cashbox,
        type='INCOME'
    ).exclude(
        description__startswith='Davomat #'
    ).filter(
        source_payment__isnull=True
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    expense = Transaction.objects.filter(
        cashbox=cashbox,
        type='EXPENSE'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    new_balance = income - expense
    if cashbox.balance != new_balance:
        Cashbox.objects.filter(pk=cashbox.pk).update(balance=new_balance)
        cashbox.balance = new_balance
    return new_balance
