# HR Employee Custom - UAE Module

## Installation on Odoo.sh
1. Upload this folder to your GitHub repo linked with Odoo.sh
2. Go to Odoo.sh → Branch → Modules
3. Install "HR Employee Custom - UAE"

## Dependencies Required
- hr (base HR)
- hr_contract
- hr_payroll (optional, for payslip links)
- hr_holidays

## Features Included

### 1. Resume Tab Changes
- "Other Experience" → "Other Experience - Resume"
- "Training" → "Interview Document"

### 2. Work Permit
- Work Permit Document upload field
- Work Permit Issue Date

### 3. Attachments Tab (New)
- Visa Attachment + Expiry Date
- Passport Attachment + Expiry Date
- Emirates ID Attachment + Expiry Date

### 4. Field Renaming
- Contract Date → Joining Date
- Wages → Basic Salary

### 5. New Fields
- Work Permit Issue Date
- Gratuity (auto-calculated: UAE law - 21 days/year for <5 yrs, 30 days/year after)

### 6. Notifications
- Daily cron runs and sends email to HR Managers
- Alert if any document expires within 1 month
- Salary Increment History tab on employee form
- Bonus & Commission History tab on employee form

### 7. Loan Module
- Standalone Loan/Advance Tracker
- Shows: Advance Collected | Paid Back | Balance to Pay
- Repayment schedule with payslip linkage

## Notes
- Gratuity is computed based on UAE Labour Law (Basic Salary / 30 = daily rate)
- Document expiry check runs daily via scheduled action
- HR Manager group receives email alerts for expiring documents
