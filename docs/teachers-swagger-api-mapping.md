# Teachers API Mapping

Source of truth: `https://xususiy.onrender.com/api/swagger/` and its OpenAPI document at `/api/schema/`.

All routes below use the configured Axios base URL and require the authenticated Bearer token unless the backend says otherwise.

## Teacher CRUD

| Method | Backend route | Frontend wrapper | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/accounts/employees/?role=teacher` | `teachersApi.getTeachers` | Load teacher list. The `role=teacher` query is applied by `fetchTeachers`. |
| POST | `/api/v1/accounts/employees/` | `teachersApi.createTeacher` | Create an employee/teacher. Supports JSON and multipart form data. |
| GET | `/api/v1/accounts/employees/{id}/` | `teachersApi` detail callers | Load one employee profile. |
| PATCH | `/api/v1/accounts/employees/{id}/` | `teachersApi.updateTeacher` | Partial teacher update. |
| PUT | `/api/v1/accounts/employees/{id}/` | Backend-supported; no separate frontend wrapper currently | Full teacher update. |
| DELETE | `/api/v1/accounts/employees/{id}/` | `teachersApi.deleteTeacher` | Delete/archive employee according to backend behavior. |
| GET | `/api/v1/accounts/employees/{id}/history/` | `teachersApi.getTeacherHistory` | Employee activity history. |

### Create/update body names

The employee serializer expects these names:

```json
{
  "first_name": "Aliyev",
  "last_name": "Vali",
  "phone": "+998901234567",
  "position": "Matematika o'qituvchisi",
  "role": "teacher",
  "branch": 1,
  "branches": [1, 2],
  "birth_date": "1995-05-15",
  "gender": "male",
  "salary_percentage": 1,
  "password": "password123"
}
```

Optional multipart field: `photo`.

`salary_percentage` is an integer `StaffSalaryPercent` ID. The backend description says a teacher salary percentage is required. Therefore the add-teacher form must select a percentage before submitting; `salary_type` and `hourly_rate` are sent when those UI options are used, but they do not replace the required percentage relation unless the backend serializer is changed.

The frontend intentionally does not send legacy aliases such as `full_name`, `phone_number`, `branch_id`, `branch_ids`, `assigned_branches`, `assigned_branch_ids`, or `roles` in the new-teacher request.

## Teacher dropdown data

| Method | Backend route | Frontend wrapper | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/organizations/branches/` | `organizationApi.getAllBranches` | Branch selector. |
| GET | `/api/v1/finance/salary-percents/` | `financeApi.salaryPercents.getAll` | Salary percentage selector. IDs from this response are sent as `salary_percentage`. |
| POST | `/api/v1/finance/salary-percents/` | `financeApi.salaryPercents.create` | Create salary percentage. Body: `{ name, percent }`. |
| PATCH | `/api/v1/finance/salary-percents/{id}/` | `financeApi.salaryPercents.update` | Edit salary percentage. |
| DELETE | `/api/v1/finance/salary-percents/{id}/` | `financeApi.salaryPercents.delete` | Delete salary percentage. |
| GET | `/api/v1/accounts/roles/` | `teachersApi.getRoles` | Available system roles. |

The salary percentage settings page is database-only: it does not seed or merge `localStorage` values. If the API fails, it displays an empty state/error instead of fabricated rates.

## Teacher groups and timetable

| Method | Backend route | Frontend wrapper | Query/body |
| --- | --- | --- | --- |
| GET | `/api/v1/academics/groups/?teacher={id}` | `teachersApi.getTeacherGroups` | Teacher's assigned groups. |
| GET | `/api/v1/academics/lesson-schedules/?teacher={id}` | `teachersApi.getTeacherSchedules`, `timetableApi` | Teacher timetable rows. |
| GET | `/api/v1/academics/lessons/calendar/?teacher_id={id}` | `teachersApi.getTeacherCalendar`, `attendanceApi`, `reportsApi` | Calendar lessons for the teacher. |
| GET | `/api/v1/academics/teachers/` | Backend-supported academic teacher resource | Alternative teacher resource documented by Swagger; current Teachers page uses employees because employee CRUD is the create contract. |

## Teacher salary and finance

| Method | Backend route | Frontend wrapper | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/finance/teacher-salary-rules/?teacher={id}` | `teachersApi.getTeacherSalaryRules`, `financeApi.salaryRules.getAll` | Salary rules for a teacher. |
| POST | `/api/v1/finance/teacher-salary-rules/` | `teachersApi.createTeacherSalaryRule`, `financeApi.salaryRules.create` | Create salary rule. |
| PATCH | `/api/v1/finance/teacher-salary-rules/{id}/` | `financeApi.salaryRules.update` | Update salary rule. |
| DELETE | `/api/v1/finance/teacher-salary-rules/{id}/` | `financeApi.salaryRules.delete` | Delete salary rule. |
| POST | `/api/v1/finance/teacher-salary/calculate/` | `teachersApi.calculateTeacherSalary`, `financeApi.salaryCalculations.calculate` | Calculate teacher salary. |
| GET | `/api/v1/finance/salary-calculations/?teacher={id}` | `teachersApi.getTeacherSalaryCalculations`, `financeApi.salaryCalculations.getAll` | Salary calculation history. |
| GET | `/api/v1/finance/teacher-salary-payments/?teacher={id}` | `teachersApi.getTeacherSalaries`, `financeApi.salaryPayments.getAll` | Paid salary history. |
| POST | `/api/v1/finance/teacher-salary-payments/` | `teachersApi.payTeacherSalary`, `financeApi.salaryCalculations.payout` | Pay salary from cashbox. |
| GET | `/api/v1/finance/teacher-salary-payments/{id}/` | `financeApi.salaryPayments.get` | One payment. |
| GET | `/api/v1/finance/teacher-salary-payments/summary/` | `financeApi.salaryPayments.getSummary` | Payment summary. |
| GET | `/api/v1/finance/teacher-debts/` | `teachersApi.getTeacherDebts`, `financeApi.teacherDebts.getAll` | Teacher debt list. |
| GET | `/api/v1/finance/teacher-debts/summary/` | `financeApi.teacherDebts.getSummary` | Teacher debt summary. |
| GET | `/api/v1/finance/analytics/teacher-efficiency/` | `teachersApi.getTeacherEfficiency`, `financeApi.analytics.getTeacherEfficiency` | Teacher efficiency analytics. |

## Confirmed non-routes

These paths are not present in the live Swagger schema and must not be used as fallback routes:

- `GET /api/v1/academics/rooms/`
- `/api/v1/finance/teacher-salary/payments/`
- `/api/v1/finance/teacher-salary-calculations/`
- `/api/v1/finance/debts/teachers/`
- `/api/v1/finance/teacher-salary/payments/summary/`

## Verification

- OpenAPI path inventory was fetched from `/api/schema/`.
- Teacher and salary API modules were aligned to the documented paths.
- `npm run build` must pass after API changes.
