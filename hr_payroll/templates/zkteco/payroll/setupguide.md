# 🎯 Payroll System Setup Guide

## ধাপ ১: Models যোগ করুন

`models.py` ফাইলে নতুন Payroll models যোগ করুন:
- `PayrollCycle`
- `PayrollRecord`
- `PayrollAdjustment`
- `PayrollPayment`
- `PayrollTemplate`

## ধাপ ২: Migration তৈরি ও রান করুন

```bash
# Migration তৈরি করুন
python manage.py makemigrations

# Migration রান করুন
python manage.py migrate
```

## ধাপ ৩: Views যোগ করুন

`views/payroll_generation_views.py` নামে নতুন ফাইল তৈরি করুন এবং সব views কোড যোগ করুন।

## ধাপ ৪: URLs কনফিগার করুন

`urls.py` ফাইলে payroll routes যোগ করুন:

```python
from .views import payroll_generation_views

# Payroll URLs যোগ করুন
```

## ধাপ ৫: Templates তৈরি করুন

নিম্নলিখিত templates তৈরি করুন:

1. `templates/zkteco/payroll/generation_dashboard.html`
2. `templates/zkteco/payroll/cycle_list.html`
3. `templates/zkteco/payroll/cycle_detail.html`

## ধাপ ৬: Admin Panel কনফিগার করুন

`admin.py` ফাইলে payroll admin classes যোগ করুন।

## ধাপ ৭: Permissions সেটআপ করুন

Django admin panel এ গিয়ে প্রয়োজনীয় permissions সেটআপ করুন:

```
- Can add payroll cycle
- Can change payroll cycle
- Can delete payroll cycle
- Can view payroll cycle
- Can add payroll record
- Can change payroll record
- Can mark as paid
```

## ধাপ ৮: Default Template তৈরি করুন

Admin panel থেকে অথবা Django shell দিয়ে একটি default payroll template তৈরি করুন:

```python
from zkteco.models import PayrollTemplate, Company

company = Company.objects.first()

PayrollTemplate.objects.create(
    company=company,
    name="Default Payroll Template",
    description="মাসিক বেতন টেমপ্লেট",
    default_cycle_type='monthly',
    payment_day=5,
    auto_calculate_overtime=True,
    auto_calculate_deductions=True,
    auto_calculate_bonuses=True,
    perfect_attendance_bonus=1000.00,
    minimum_attendance_for_bonus=95.0,
    per_day_absence_deduction_rate=100.0,
    late_arrival_penalty=50.00,
    is_active=True
)
```

## ধাপ ৯: Navigation Menu আপডেট করুন

আপনার base template এ payroll link যোগ করুন:

```html
<a href="{% url 'zkteco:payroll_dashboard' %}">
    <svg>...</svg>
    পেরোল ম্যানেজমেন্ট
</a>
```

## ধাপ ১০: Testing

### প্রথম Payroll তৈরি করুন:

1. `/payroll/` এ যান
2. "পেরোল তৈরি করুন" বাটনে ক্লিক করুন
3. তারিখ রেঞ্জ নির্বাচন করুন (যেমন: এই মাসের ১ তারিখ থেকে শেষ তারিখ)
4. কর্মচারী/বিভাগ ফিল্টার করুন (ঐচ্ছিক)
5. "প্রিভিউ দেখুন" ক্লিক করুন
6. প্রিভিউ চেক করুন
7. "পেরোল জেনারেট করুন" ক্লিক করুন

### যাচাই করুন:

- ✅ সব কর্মচারীর বেতন সঠিকভাবে গণনা হয়েছে কিনা
- ✅ উপস্থিতি তথ্য সঠিক কিনা
- ✅ ওভারটাইম সঠিকভাবে হিসাব হয়েছে কিনা
- ✅ কর্তন সঠিক কিনা
- ✅ নেট বেতন সঠিক কিনা

## 🎨 Features

### ✨ Core Features:

1. **পেরোল জেনারেশন**
   - মাসিক/সাপ্তাহিক/পাক্ষিক
   - স্বয়ংক্রিয় হিসাব
   - প্রিভিউ সিস্টেম

2. **উপস্থিতি ভিত্তিক হিসাব**
   - উপস্থিত/অনুপস্থিত গণনা
   - ছুটির দিন বিবেচনা
   - অনুপস্থিতি কর্তন

3. **ওভারটাইম ম্যানেজমেন্ট**
   - স্বয়ংক্রিয় ওভারটাইম হিসাব
   - কাস্টম রেট
   - ঘণ্টাভিত্তিক মজুরি

4. **বোনাস ও ভাতা**
   - উপস্থিতি বোনাস
   - উৎসব বোনাস
   - বিভিন্ন ধরনের ভাতা

5. **কর্তন ম্যানেজমেন্ট**
   - ভবিষ্য তহবিল
   - কর কর্তন
   - ঋণ কর্তন
   - অনুপস্থিতি কর্তন

6. **পেমেন্ট ট্র্যাকিং**
   - পেমেন্ট স্ট্যাটাস
   - পেমেন্ট পদ্ধতি
   - রেফারেন্স নম্বর

7. **রিপোর্টিং**
   - CSV এক্সপোর্ট
   - বিস্তারিত রিপোর্ট
   - পেমেন্ট রিপোর্ট

8. **টেমপ্লেট সিস্টেম**
   - পূর্ব-সংজ্ঞায়িত নিয়ম
   - কাস্টম সেটিংস
   - রিইউজেবল কনফিগারেশন

## 📊 Database Schema

```
PayrollCycle (পেরোল সাইকেল)
├── company
├── name
├── start_date / end_date
├── status (draft/generated/approved/paid/closed)
├── total_gross_salary
├── total_net_salary
└── total_deductions

PayrollRecord (পেরোল রেকর্ড)
├── payroll_cycle
├── employee
├── basic_salary + allowances
├── overtime_hours + overtime_amount
├── deductions
├── gross_salary / net_salary
├── payment_status
└── attendance_data

PayrollAdjustment (সমন্বয়)
├── payroll_record
├── adjustment_type (addition/deduction)
├── title / amount
└── description

PayrollPayment (পেমেন্ট)
├── payroll_record
├── amount / payment_date
├── payment_method
├── reference_number
└── status

PayrollTemplate (টেমপ্লেট)
├── company
├── name / settings
├── bonus_rules
├── deduction_rules
└── auto_calculation_flags
```

## 🔧 Configuration Options

### Payroll Template Settings:

```python
{
    'default_cycle_type': 'monthly',  # monthly/weekly/biweekly
    'payment_day': 5,  # মাসের যে দিন পেমেন্ট হবে
    'auto_calculate_overtime': True,
    'auto_calculate_deductions': True,
    'auto_calculate_bonuses': True,
    'perfect_attendance_bonus': 1000.00,
    'minimum_attendance_for_bonus': 95.0,
    'per_day_absence_deduction_rate': 100.0,
    'late_arrival_penalty': 50.00,
}
```

## 🚀 API Endpoints

```
GET  /payroll/                              # Dashboard
POST /payroll/preview/                      # Generate preview
POST /payroll/generate/                     # Generate records
GET  /payroll/cycles/                       # List cycles
GET  /payroll/cycles/<id>/                  # Cycle detail
GET  /payroll/cycles/<id>/export/           # Export CSV
POST /payroll/records/<id>/mark-paid/       # Mark as paid
```

## 💡 Usage Examples

### Example 1: মাসিক পেরোল তৈরি

```python
# Manual creation via Django shell
from zkteco.models import PayrollCycle, Employee
from datetime import date
from decimal import Decimal

cycle = PayrollCycle.objects.create(
    company=company,
    name="জানুয়ারি ২০২৫ পেরোল",
    start_date=date(2025, 1, 1),
    end_date=date(2025, 1, 31),
    cycle_type='monthly',
    status='draft'
)

# Generate records for all employees
employees = Employee.objects.filter(company=company, is_active=True)
for employee in employees:
    PayrollRecord.objects.create(
        payroll_cycle=cycle,
        employee=employee,
        basic_salary=employee.basic_salary,
        # ... other fields
    )
```

### Example 2: পেমেন্ট মার্ক করা

```python
from zkteco.models import PayrollRecord

records = PayrollRecord.objects.filter(
    payroll_cycle__id=1,
    payment_status='pending'
)

for record in records:
    record.payment_status = 'paid'
    record.payment_date = date.today()
    record.save()
```

### Example 3: কাস্টম Adjustment যোগ করা

```python
from zkteco.models import PayrollAdjustment

PayrollAdjustment.objects.create(
    payroll_record=record,
    adjustment_type='addition',
    title='বিশেষ বোনাস',
    amount=Decimal('5000.00'),
    description='প্রজেক্ট সফলতার জন্য',
    created_by=request.user
)
```

## 🐛 Troubleshooting

### সমস্যা: Attendance data পাওয়া যাচ্ছে না

**সমাধান:** 
- নিশ্চিত করুন Attendance records generate করা আছে
- তারিখ রেঞ্জ চেক করুন
- AttendanceLog থেকে data import হয়েছে কিনা দেখুন

### সমস্যা: ওভারটাইম হিসাব ভুল

**সমাধান:**
- Employee এর `overtime_rate` চেক করুন
- AttendanceProcessorConfiguration দেখুন
- Manual calculation করে verify করুন

### সমস্যা: Template apply হচ্ছে না

**সমাধান:**
- Template `is_active = True` কিনা চেক করুন
- Template selection করা হয়েছে কিনা দেখুন
- Cache clear করুন

## 📝 Best Practices

1. ✅ সবসময় প্রথমে Preview দেখুন
2. ✅ Backup নিয়ে তারপর Generate করুন
3. ✅ Monthly cycle একবারে generate করুন
4. ✅ Payment করার আগে double-check করুন
5. ✅ Template ব্যবহার করুন consistency এর জন্য
6. ✅ Regular audit করুন
7. ✅ CSV export করে record রাখুন

## 🎓 Next Steps

1. **Advanced Features যোগ করুন:**
   - Tax calculation automation
   - Provident fund management
   - Loan management system
   - Performance-based bonuses

2. **Integration:**
   - Bank API integration
   - Mobile banking integration
   - Email notifications
   - SMS alerts

3. **Reporting:**
   - Advanced analytics
   - Trend analysis
   - Department-wise reports
   - Year-end reports

---

**সফল পেরোল ম্যানেজমেন্টের জন্য শুভকামনা! 🎉**