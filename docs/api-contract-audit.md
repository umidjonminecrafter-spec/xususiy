# Full API Contract Audit

Source of truth: live Swagger/OpenAPI at `https://xususiy.onrender.com/api/swagger/` and `/api/schema/`.

## Fixed mismatches

- Student leave now uses `/api/v1/academics/student-group-leaves/`.
- Student balance uses `/api/v1/academics/student-balances/`.
- Student archive/restore uses `/api/v1/academics/archive/` and `/api/v1/academics/archive/{id}/restore/`.
- Student payment history uses `/api/v1/finance/payments/?student={id}`.
- Student salary/SMS history no longer calls undocumented routes.
- Homework uses only `/api/v1/academics/homeworks/`.
- Buildings use `/api/v1/organizations/buildings/` or documented `/api/v1/settings/buildings/`; `/api/v1/academics/buildings/` was removed.
- Forgot-password confirmation uses `/api/v1/accounts/forgot-password/confirm/`; undocumented reset fallback was removed.
- Student debt uses `/api/v1/finance/student-debts/` and its summary route.
- Profit chart uses `/api/v1/finance/profit-chart/`.
- Finance analytics uses documented `student-left-reasons/`, `branches/`, and `rooms/` routes.
- Teacher salary calculations/payments/debts use the documented `/finance/salary-calculations/`, `/finance/teacher-salary-payments/`, and `/finance/teacher-debts/` routes.
- Salary percentage settings use `/api/v1/finance/salary-percents/` and database-only data.

## Domains confirmed against Swagger

These domains have matching documented route families in the source:

- Accounts/auth/employees/roles
- Organizations, branches, buildings, subscriptions, tariffs, settings
- Academics students, groups, courses, rooms, lesson schedules, lessons, attendance, exams, holidays, homeworks, course materials
- Finance payments, expenses, salaries, salary percentages, salary rules, calculations, teacher payments, debts, analytics
- CRM leads, pipelines, forms, sources, activities, messages
- Communication messages, SMS, templates, schedules, notifications, providers
- Tasks boards, columns, items, comments, checklists, labels, attachments, permissions, history
- Support FAQ, chat, history, tickets
- KPI templates, goals, sub-goals, logs
- Reports and attendance analytics

## Backend routes absent from live Swagger

These frontend features cannot be connected to the live database until the backend publishes a route:

The class page must not claim that class CRUD is connected until the backend adds a class resource. The current class UI can load its teacher/building auxiliary data, but cannot persist classes through a documented API.

## Important contract rules

- Employee teacher creation uses `/api/v1/accounts/employees/`.
- Teacher list must include `?role=teacher`.
- Employee creation uses `first_name`, `last_name`, `phone`, `position`, `role`, `branch`, `branches`, `birth_date`, `gender`, `salary_percentage`, `hourly_rate`, `password`, and optional `photo`.
- `salary_percentage` is an integer StaffSalaryPercent ID and is required by the live teacher serializer.
- Do not send fabricated local seed data as backend data.
- Do not use undocumented fallback paths to hide a 404.

## Validation

The repository build is the executable validation for the route-wrapper edits:

```text
npm run build
```
