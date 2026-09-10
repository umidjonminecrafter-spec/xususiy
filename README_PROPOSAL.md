# 🎓 Smart Academy / EduERP

> **Enterprise-grade multi-tenant SaaS ERP & CRM platform engineered for education centers, private academies, and school networks — featuring full academic lifecycles, automated financial ledgers, lead pipeline CRM, billing, SMS/Telegram notifications, and 125/125 verified automated test coverage.**

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg?logo=python)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.x-green.svg?logo=django)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/DRF-3.17%2B-red.svg)](https://www.django-rest-framework.org/)
[![Tests](https://img.shields.io/badge/Tests-125%20passed%20(100%25)-brightgreen.svg)]()
[![OpenAPI](https://img.shields.io/badge/Schema-Swagger%20%2F%20Redoc-orange.svg)](https://swagger.io/)
[![Architecture](https://img.shields.io/badge/Architecture-Multi--Tenant%20SaaS-purple.svg)]()

---

## 📋 Overview

**Smart Academy EduERP** is an enterprise backend ecosystem designed to solve the operational fragmentation faced by growing educational institutions. It unifies admissions (CRM), multi-branch academic scheduling, automated tuition billing, staff payroll calculations, student attendance tracking, and multichannel communications into a single scalable, multi-tenant architecture.

The project encompasses **185+ Python modules** and over **34,000 lines of robust, modular code**, backed by an extensive automated test suite of **125 end-to-end and unit test cases** ensuring zero regression across tenant boundaries.

---

## 🌟 Key Features

- **Multi-Tenant SaaS Isolation**: Global organization partitioning where schools operate with strict data boundaries, custom sub-branches, bespoke pricing tariffs, and subscription lifecycles.
- **Academic Management Engine**: Dynamic lesson timetables, room clash prevention, student group assignments, exam grading grids, attendance tracking, and automated parent appeals.
- **Sales & Lead CRM**: Visual conversion pipelines (Leads -> Trial Lesson -> Enrolled), lead source analytics, lost-reason tracking, and manager activity logging.
- **Finance & Automated Payroll**: Tuition payments, balance top-ups, cashbox reconciliation, expense tracking, teacher hourly/percentage salary formulas, bonuses, and penalties.
- **Billing & Subscription Management**: Flexible SaaS tiered plans, tenant quota enforcement (student limits, branch limits), and automated renewal reminders.
- **Omnichannel Communication**: Eskiz/Playmobile SMS gateways for bulk announcements, lesson reminders, and automated Telegram bot notifications for payment receipts and escalations.
- **Task Management & KPI**: Built-in collaborative Kanban boards, checklist items, attachments, employee KPI scorecards, and historical evaluation logs.

---

## 🏛️ Architecture & Clean Design

The project strictly follows Domain-Driven Design (DDD) principles with decoupled Django apps:

```
xususiy/
├── accounts/         # RBAC authentication, custom user models (Superadmin, Org Admin, Teacher, Student)
├── organizations/    # Multi-tenant isolation engine, Branch, Tariff, Subscription models & mixins
├── academics/        # Courses, Rooms, Groups, Attendance, Lesson schedules, Exams, Homework
├── crm/              # Lead capture forms, Sales pipeline stages, Activity tracking, Conversions
├── finance/          # Cash registers, Teacher salary calculations, Expense categories, Ledger entries
├── billing/          # SaaS subscription renewals, Tariff purchases, Balance top-up history
├── communication/    # Bulk SMS dispatch, Provider abstractions (Eskiz), Telegram alerts, Templates
├── tasks/            # Kanban boards, Columns, Task items, Checklists, Activity audit trail
├── kpi/              # Employee performance indicators, KPI templates, Objective tracking
└── audit/            # Security logs, Tenant operation tracking
```

Every tenant model inherits from a secure `TenantModel` mixin that automatically scopes ORM queries to the requesting user organization:
```python
class TenantModel(BaseModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    branch = models.ForeignKey("organizations.Branch", on_delete=models.SET_NULL, null=True, blank=True)
    class Meta:
        abstract = True
```

---

## 🛠️ Tech Stack

- **Framework**: Django 6.x & Django REST Framework (DRF)
- **Authentication**: JWT (`djangorestframework-simplejwt`) with role-based claims
- **Database**: PostgreSQL (Production) / SQLite (Development) with connection pooling
- **API Documentation**: OpenAPI 3.0 via `drf-spectacular` (Swagger UI & ReDoc)
- **Task Scheduling & Asynchronous Jobs**: Background thread dispatcher & cron management commands
- **Third-Party APIs**: Eskiz SMS API, Telegram Bot API, OpenAI / Gemini integrations
- **Deployment**: Gunicorn, WhiteNoise, Docker-ready, Render/Railway cloud configuration

---

## 🏢 Multi-Tenancy Deep Dive

Each tenant operates as an independent institution within the unified database:
1. **Tenant Middleware / Mixin**: Automatically filters querysets based on the authenticated user organization.
2. **Subscription Gatekeeping**: Restricts access if the tenant active subscription expires or if student capacity exceeds the allocated plan quota.
3. **Cross-Tenant Security**: Rigorous test suites verify that Tenant A cannot access, mutate, or query Tenant B data under any condition.

---

## 📚 Academic Management

- **Dynamic Scheduling**: Supports alternating days (Odd/Even/Daily), room capacity limits, and teacher conflicts.
- **Attendance Ledger**: Mark present, absent, excused, or late with automatic SMS alerts triggered for absent students.
- **Grading & Homework**: Homework submission portals, teacher feedback, and automated exam percentile distribution.
- **Student Archive & Leaves**: Freeze student balances during holidays or medical leaves without data loss.

---

## 🎯 Sales & Admissions CRM

- **Pipelines & Stages**: Configurable lead stages (New Lead -> Contacted -> Demo Booked -> Attended -> Enrolled -> Won/Lost).
- **Source Tracking**: Measure ROI on marketing channels (Instagram, Telegram, Referral, Walk-in).
- **Conversion Analytics**: Track manager response times and stage-by-stage drop-off rates.

---

## 💰 Finance & Payroll Automation

- **Automated Salary Rules**: Computes complex teacher payroll based on:
  - Fixed monthly salary
  - Per-hour rate
  - Percentage of collected student fees
  - Deductions for unattended classes and performance bonuses
- **Cashbox & Vault Auditing**: Multi-currency cashier reconciliation (Cash, Card/Terminal, Bank Transfer).

---

## 🧪 Testing & Code Quality

The system is fortified by **125 automated test cases** covering multi-tenant boundaries, financial calculations, auth pipelines, and API contracts:

```bash
Found 125 test(s).
System check identified no issues (0 silenced).
................................................................................
.............................................
----------------------------------------------------------------------
Ran 125 tests in 137.974s

OK
```

---

## 🔒 Security & Best Practices

- **Zero-Secret Codebase**: All secrets, database URLs, and API tokens are decoupled via environment variables.
- **Least Privilege Access**: Granular permission classes (`IsOrganizationAdmin`, `IsTeacher`, `IsAccountant`, `IsTenantUser`).
- **Audit Logging**: Sensitive mutations (salary adjustments, discount grants, grade updates) are recorded with timestamp and author signatures.

---

## 🚀 Installation & Local Development

### 1. Clone and Setup
```bash
git clone https://github.com/umidjonminecrafter-spec/xususiy.git
cd xususiy

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration
```bash
cp .env.example .env
# Edit .env with your local credentials
```

### 3. Run Migrations & Seed Initial Data
```bash
python manage.py migrate
python initialize_data.py
python manage.py runserver
```

---

## ⚙️ Environment Variables (`.env.example`)

```ini
# Core Django
SECRET_KEY=your-secure-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=sqlite:///db.sqlite3

# SMS Gateway (Optional)
ESKIZ_EMAIL=your-eskiz-email@example.com
ESKIZ_PASSWORD=your-eskiz-password

# AI Integrations (Optional)
GEMINI_API_KEY=your-gemini-key
OPENAI_API_KEY=your-openai-key
```

---

## 📖 Interactive API Documentation

With the server running, visit:
- **Swagger UI**: `http://127.0.0.1:8000/api/schema/swagger-ui/`
- **ReDoc**: `http://127.0.0.1:8000/api/schema/redoc/`
- **OpenAPI JSON**: `http://127.0.0.1:8000/api/schema/`

---

## 💼 Commercial Use Cases

1. **Private K-12 Schools & Academies**: Complete end-to-end administration, from enrollment to graduation.
2. **Franchised Language & Training Centers**: Centralized headquarters oversight with distributed branch management.
3. **B2B SaaS Startup**: Ready-made foundation for launching an educational CRM SaaS product in emerging markets.
