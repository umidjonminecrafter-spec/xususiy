from django.urls import path, include
from rest_framework.routers import DefaultRouter
from finance.views import (
    ExpenseCategoryViewSet, ExpenseSubcategoryViewSet, ExpenseViewSet,
    DetailedExpenseViewSet, MonthlyIncomeViewSet, PaymentViewSet, SaleViewSet,
    BonusViewSet, FineViewSet, SalaryViewSet, TeacherSalaryRuleViewSet,
    TeacherSalaryCalculationViewSet, TeacherSalaryCalculateView, TeacherSalaryPaymentsView,
    StudentDebtsView, StudentDebtsSummaryView, StudentDebtDetailView,
    TeacherDebtsView, TeacherDebtsSummaryView, AllDebtsView, CashboxViewSet, FinanceReportView,
    WithdrawalViewSet, ConversionReportsFunnelView, CRMLeadsListView,
    ConversionReportsOverviewView, ConversionReportsLostReasonsView, ConversionReportsPipelineTransitionsView,
    LeadsReportPieChartView, LeadsReportBarChartView, LeadsReportStatisticsView, CompanyProfitChartView, LeadsReportDetailedView,
    FinanceActionViewSet, temp_log_view, TeacherWorkLogViewSet
)

from finance.views import StaffSalaryPercentViewSet, FinanceSettingAPIView, FinancialReportsView, \
    FinancialAnalyticsView, TransactionReportAPIView, TransactionCreateAPIView, AdvancedPaymentReportAPIView, \
    CashboxListCreateAPIView, CashTransferAPIView

from finance.views import CashFlowReportView, TransactionViewSet, TransactionTypesView, \
    EmployeeFinanceBalanceReportView, DiscountsAndBonusesReportView,UnsubmittedAttendanceReportView,RoomAnalyticsReportView
from finance.views import TransactionCategoryViewSet, PnLReportView, RevenuePlanReportView, UnpaidLessonsReportView, \
    CancelledPaymentsReportView,TeacherEfficiencyReportView,AdministratorEfficiencyReportView,StudentLeaversReasonsReportView,BranchMonitoringReportView

router = DefaultRouter()
router.register(r'salary-percents', StaffSalaryPercentViewSet, basename='salary-percent')
router.register(r'expense-categories', ExpenseCategoryViewSet, basename='expense-category')
router.register(r'actions', FinanceActionViewSet, basename='finance-actions')
router.register(r'expense-subcategories', ExpenseSubcategoryViewSet, basename='expense-subcategory')
router.register(r'expenses', ExpenseViewSet, basename='expense')
router.register(r'detailed-expenses', DetailedExpenseViewSet, basename='detailed-expense')
router.register(r'monthly-income', MonthlyIncomeViewSet, basename='monthly-income')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'sales', SaleViewSet, basename='sale')
router.register(r'bonuses', BonusViewSet, basename='bonus')
router.register(r'fines', FineViewSet, basename='fine')
router.register(r'salaries', SalaryViewSet, basename='salary')
router.register(r'teacher-salary-rules', TeacherSalaryRuleViewSet, basename='teacher-salary-rule')
router.register(r'teacher-work-logs', TeacherWorkLogViewSet, basename='teacher-work-log')
router.register(r'salary-calculations', TeacherSalaryCalculationViewSet, basename='teacher-salary-calculation')
router.register(r'teacher-salary-payments', TeacherSalaryPaymentsView, basename='teacher-salary-payment')
router.register(r'cashboxes', CashboxViewSet, basename='cashbox')
router.register(r'transactions-types-crud', TransactionCategoryViewSet, basename='transaction-category')
router.register(r'withdrawals', WithdrawalViewSet, basename='withdrawal')
router.register(r'transactions', TransactionViewSet, basename='transactions')

urlpatterns = [
    path('teacher-salary/calculate/', TeacherSalaryCalculateView.as_view(), name='teacher-salary-calculate'),
    path('salary/calculate/', TeacherSalaryCalculateView.as_view(), name='salary-calculate'),
    path('report/', FinanceReportView.as_view(), name='finance-report'),
    path('profit-chart/', CompanyProfitChartView.as_view(), name='company-profit-chart'),
    path('settings/', FinanceSettingAPIView.as_view(), name='finance-settings'),

    path('student-debts/summary/', StudentDebtsSummaryView.as_view(), name='student-debts-summary'),
    path('student-debts/', StudentDebtsView.as_view(), name='student-debts-list'),
    path('student-debts/<int:pk>/', StudentDebtDetailView.as_view(), name='student-debts-detail'),
    path('cashboxes/', CashboxListCreateAPIView.as_view(), name='cashbox-list-create'),
    path('financial-reports/', FinancialReportsView.as_view(), name='financial-reports'),

    path('payments/report/', AdvancedPaymentReportAPIView.as_view(), name='payments-report'),
    path('teacher-debts/summary/', TeacherDebtsSummaryView.as_view(), name='teacher-debts-summary'),
    path('teacher-debts/', TeacherDebtsView.as_view(), name='teacher-debts-list'),
    path('transactions/create/', TransactionCreateAPIView.as_view(), name='transaction-create'),
    path('transactions/transfer/', CashTransferAPIView.as_view(), name='transaction-transfer'),

    path('transactions/report/', TransactionReportAPIView.as_view(), name='transaction-report'),
    path('all-debts/', AllDebtsView.as_view(), name='all-debts'),
    path('analytics/', FinancialAnalyticsView.as_view(), name='financial-analytics'),

    # 🌟 TO'G'RILANDI: PnL va barcha kerakli hisobot yo'llari urlpatterns ichida
    path('reports/pnl/', PnLReportView.as_view(), name='pnl-report'),
    path('conversion-reports/funnel/', ConversionReportsFunnelView.as_view(), name='conversion-reports-funnel'),
    path('conversion-reports/overview/', ConversionReportsOverviewView.as_view(), name='conversion-reports-overview'),
    path('conversion-reports/lost-reasons/', ConversionReportsLostReasonsView.as_view(),
         name='conversion-reports-lost-reasons'),
    path('conversion-reports/pipeline-transitions/', ConversionReportsPipelineTransitionsView.as_view(),
         name='conversion-reports-pipeline-transitions'),
    path('crm-leads/', CRMLeadsListView.as_view(), name='crm-leads-list'),

    path('leads-report/pie-chart/', LeadsReportPieChartView.as_view(), name='leads-report-pie-chart'),
    path('leads-report/bar-chart/', LeadsReportBarChartView.as_view(), name='leads-report-bar-chart'),
    path('leads-report/statistics/', LeadsReportStatisticsView.as_view(), name='leads-report-statistics'),
    path('leads-report/detailed-report/', LeadsReportDetailedView.as_view(), name='leads-report-detailed'),

    path('reports/cash-flow/', CashFlowReportView.as_view(), name='report-cash-flow'),
    path('reports/employee-balance/', EmployeeFinanceBalanceReportView.as_view(), name='report-employee-balance'),
    path('reports/revenue-plan/', RevenuePlanReportView.as_view(), name='report-revenue-plan'),
    path('reports/unpaid-payments/', UnpaidLessonsReportView.as_view(), name='report-unpaid-payments'),
    path('reports/cancelled-payments/', CancelledPaymentsReportView.as_view(), name='report-cancelled-payments'),
    path('reports/discounts-bonuses/', DiscountsAndBonusesReportView.as_view(), name='report-discounts-bonuses'),
    path('analytics/rooms/', RoomAnalyticsReportView.as_view(), name='room-analytics'),
    path('analytics/branches/', BranchMonitoringReportView.as_view(), name='branch-monitoring'),
    path('analytics/unsubmitted-attendance/', UnsubmittedAttendanceReportView.as_view(), name='unsubmitted-attendance'),

    path('analytics/teacher-efficiency/', TeacherEfficiencyReportView.as_view(), name='teacher-efficiency-report'),
    path('analytics/admin-efficiency/', AdministratorEfficiencyReportView.as_view(), name='admin-efficiency-report'),
    path('analytics/student-left-reasons/', StudentLeaversReasonsReportView.as_view(), name='student-left-reasons-report'),
    path('transactions/types/', TransactionTypesView.as_view(), name='transaction-types'),
    path('temp-log/', temp_log_view, name='temp-log'),
    path('', include(router.urls)),
]