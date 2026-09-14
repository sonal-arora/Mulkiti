# HR Employee Probation Workflow

Adds a **Probation → Confirmed (Regular)** workflow to the standard Employee form.

## Dependencies
- `hr` (base HR only — no `hr_contract` / `hr_payroll` required)

## Fields added on `hr.employee`
| Field | Type | Notes |
|---|---|---|
| `probation_end_date` | Date | Set by HR (e.g. joining date + 3/6 months) |
| `employment_status` | Selection: Probation / Confirmed | Default `Probation`, shown as a badge |
| `confirmation_date` | Date (readonly) | Auto-stamped when confirmed |
| `probation_completed` | Boolean (computed, hidden) | True once `probation_end_date` has passed and status is still Probation |

## Workflow
1. New employee is created → status defaults to **Probation**. HR sets `probation_end_date`.
2. Once `probation_end_date` passes without confirmation, the form shows a warning banner
   ("Probation period has ended...").
3. HR (member of `hr.group_hr_user`) clicks the **Confirm as Regular** stat button on the
   form → status becomes **Confirmed**, `confirmation_date` is stamped, and a note is logged
   in the chatter. This is a one-way transition.
4. A daily scheduled action (`Employee Probation Reminder`) emails + chatter-notifies all HR
   users at **14 / 7 / 1 days before**, and again **on** the probation end date, for any
   employee still in Probation.

## Access
The **Confirm as Regular** button is only visible to users in the `hr.group_hr_user`
(HR Officer/Manager) group.
