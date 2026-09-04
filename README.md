# Branch Accounting Approval

## Overview

**Branch Accounting Approval** adds a controlled approval workflow for **vendor bills**, **customer invoices**, and **journal entries** in **Odoo 19**.

Before a supported accounting document can be posted, the module can require approval based on one of the following routes:

- **Auditor Only**
- **CEO Only**
- **Branch then CEO**
- **Branch Only**
- **Not Required** *(restricted bypass route for approval admins/accounting managers)*

The **Auditor Only** route sends the draft vendor bill, customer invoice, or manual journal entry directly to the configured **Auditor User** before posting. For bills, credit notes, invoices, and manual journal entries that use Branch/CEO routes, the module also supports a final **Auditor Approval** stage after posting.

The module is designed for branch-based accounting teams that need clear routing, visibility controls, activity notifications, and a complete audit trail before and after posting.

> **Technical note:** the internal module folder remains `branch_bill_approval` so existing databases can upgrade safely. Only the user-facing module name, app description, README, and marketing banner were renamed.

## Key Features

- Approval route selection directly on vendor bills, vendor credit notes, customer invoices, customer credit notes, and journal entries
- Configurable company-level **Branch Approver**, **CEO Approver**, and **Auditor User**
- Auditor-only, Branch-only, CEO-only, and Branch-then-CEO approval flows before posting
- Final Auditor approval workflow for posted bills, credit notes, invoices, and manual journal entries that use Branch/CEO routes
- Auditor actions: **Approve** and **Reject**
- Auditor rejection with mandatory reason/recommendation
- Auditor-rejected draft Auditor-only documents are marked rejected; auditor-rejected posted bills, credit notes, invoices, and manual journal entries are reset to draft so the user can correct and resubmit
- Posting restriction until the selected approval route is fully completed
- Submitter tracking, including who submitted the document and when
- Current approver tracking through the **Waiting For** field, including the Auditor stage
- Personal visibility for the creator/submitter, including their own bills, invoices, and journal entries waiting for CEO or Auditor approval
- CEO-pending documents are hidden from the configured Branch Approver when the branch approver is not the creator/submitter and is not also the CEO approver
- Automatic approver activities when a document is waiting for Branch, CEO, or Auditor approval
- Automatic submitter activity after final pre-posting approval so the submitter knows the document is ready to post
- Automatic submitter notification when the Auditor rejects a draft Auditor-only document or a posted accounting document
- Reset Approval button for pending, approved-but-unposted, or rejected documents, available to the submitter/creator and accounting approval admins
- Protection against manually resetting posted accounting documents while they are waiting for Auditor approval; they must be reset through Auditor rejection
- Approval ribbons on the accounting document form: **To Approval**, **Ready to Post**, **Waiting Auditor**, **Auditor Approved**, **Rejected**, and **Rejected by Auditor**
- Search filters for personal requests, entries waiting approval, documents assigned to the current approver, ready-to-post documents, rejected requests, waiting Auditor approval, and Auditor-rejected entries
- Group By shortcuts for Approval Status, Approval Route, Waiting For, Auditor, and Submitted By
- Approval audit fields and chatter logging for submission, Branch/CEO approval, Auditor approval, posting, rejection, and final completion
- Protected workflow fields to prevent direct approval-state tampering through import/API writes
- Approver snapshot fields so changing company approvers does not unexpectedly reroute already-submitted documents
- Protection against editing key accounting fields after approval until the approval is reset

## Approval Routes

### Auditor Only
The document is routed directly to the configured **Auditor User** while it is still in draft. After the Auditor approves, the submitter receives a ready-to-post activity. If the Auditor rejects it, the document is marked rejected and the rejection reason/recommendation is kept on the document.

### Not Required
The accounting document does not require approval. For safety, only users in **Accounting Approval Admin** or **Accounting Manager** can select/post documents through this bypass route.

### Branch Only
The document must be approved by the configured **Branch Approver**. After approval, the submitter receives an activity/notification to review and post the document.

### Branch then CEO
The document must first be approved by the **Branch Approver**, then by the **CEO Approver**. After branch approval, the document moves to CEO approval. It is hidden from the configured Branch Approver unless that same user created/submitted the document or is also the configured CEO Approver. After CEO approval, the submitter receives an activity/notification to post the document.

### CEO Only
The document is routed directly to the **CEO Approver**. After CEO approval, the submitter receives an activity/notification to post the document.

### Final Auditor Approval After Posting
If an **Auditor User** is configured on the company, a bill, invoice, or manual journal entry using a Branch/CEO route is forwarded to the Auditor after it is posted. Documents using **Auditor Only** are not forwarded a second time after posting.

The Auditor can:

- **Approve** the posted accounting document. The workflow is completed and a chatter message is posted: `Auditor Approved by [Auditor User Name]`.
- **Reject** the posted accounting document with a reason or recommendation. The document is reset to draft, the original user is notified, the rejection reason is posted in the chatter, and the user can correct it and submit it again from the beginning.

## Installation / Upgrade

1. Copy the module into your Odoo custom addons path.
2. Restart the Odoo server.
3. Update the apps list.
4. Install or upgrade **Branch Accounting Approval** from the Apps menu.

Command-line upgrade example:

```bash
./odoo-bin -c /path/to/odoo.conf -d your_database_name -u branch_bill_approval --stop-after-init
```

After replacing Python files, always restart the Odoo service before testing. Odoo loads Python model code at server startup.

## Configuration

Go to **Settings / Companies**, open the target company, and configure:

- **Branch Approver**
- **CEO Approver**
- **Auditor User**

The Branch and CEO approvers are used before posting according to the selected route. The Auditor User is used before posting for **Auditor Only** documents and after posting for bills, credit notes, invoices, and manual journal entries that completed a Branch/CEO route.

Approvers are copied onto the accounting document when it is submitted. This keeps already-submitted documents assigned to the original approver even if the company configuration is changed later.

## Usage

1. Create a vendor bill, vendor credit note, customer invoice, customer credit note, or journal entry.
2. Select the required **Approval Route**.
3. Click **Submit for Approval**.
4. The assigned Branch, CEO, or Auditor approver receives an activity.
5. The approver can approve or reject the document.
6. Once the selected pre-posting route is completed, the submitter receives a **ready to post** activity.
7. The submitter reviews and posts the document.
8. For bills, credit notes, invoices, and manual journal entries using Branch/CEO routes with an Auditor configured, the posted document is forwarded to the Auditor for final review.
9. The Auditor approves to complete the final review or rejects with a recommendation.
10. If a posted accounting document is rejected by the Auditor, it returns to draft and can be corrected and submitted again from the beginning.

If a submitted document must be changed before posting, the submitter/creator or an approval admin can click **Reset Approval**, update the document, and submit it again. Rejected documents also show the rejection reason before reset.

## Filters Added

The module adds approval filters to the accounting document search views, including:

- **Waiting My Approval**: documents currently assigned to the current user as Branch, CEO, or Auditor approver
- **My Requests Waiting Approval**: bills, invoices, and journal entries created or submitted by the current user and still waiting approval
- **My Bills Waiting Approval**
- **My Invoices Waiting Approval**
- **My Journal Entries Waiting Approval**
- **Waiting Auditor Approval**: Auditor-only draft documents or posted accounting documents waiting for Auditor review
- **Rejected by Auditor**: documents rejected by the Auditor; posted accounting documents are reset to draft for correction
- **Approved / Ready to Post**: approved documents created or submitted by the current user that still need posting
- **My Rejected Requests**
- Group By options for **Approval Status**, **Approval Route**, **Waiting For**, **Auditor**, and **Submitted By**

## Functional Notes

- The approval workflow applies to `in_invoice`, `in_refund`, `out_invoice`, `out_refund`, and `entry` account moves.
- The **Auditor Only** route applies to vendor bills, vendor credit notes, customer invoices, customer credit notes, and journal entries while they are still in draft.
- The final Auditor workflow applies to posted vendor bills, vendor credit notes, customer invoices, customer credit notes, and manual `entry` journal entries when an Auditor User is configured and the document used a Branch/CEO route.
- Documents with the **Not Required** route can bypass approval only for Accounting Approval Admins or Accounting Managers.
- Documents in approval cannot be posted until the selected approval route is fully approved.
- Key accounting document fields are protected after submission, including approved-but-unposted documents; reset approval first if changes are needed.
- Direct writes/imports to internal workflow fields such as approval state, approver, approval dates, and rejection fields are blocked.
- Auditor-rejected documents keep the Auditor recommendation for correction; posted accounting documents are returned to draft.
- A creator/submitter keeps access to their own request while it is waiting for approval.
- CEO-pending documents remain hidden from other configured Branch Approvers.
- When a document is posted, the module clears its **Ready to Post** approval activity.
- Posted accounting documents waiting for Auditor approval cannot be manually reset to draft through the normal reset action; they must be rejected by the Auditor so the rejection reason is captured.

## Technical Summary

The module extends `account.move` to add:

- approval route and state tracking
- submitter tracking
- current approver tracking
- ready-to-post tracking
- company approver snapshots for Branch, CEO, and Auditor
- Auditor-only pre-posting approval
- Auditor forwarding after bill, invoice, and manual journal entry posting for Branch/CEO routes
- Auditor approve/reject actions
- Auditor rejection reason/recommendation tracking
- reset-to-draft flow after Auditor rejection
- approver and submitter activities
- posting validation before selected-route final approval
- form ribbons for approval and audit visibility
- search filters and group-by shortcuts for approval monitoring
- record-rule visibility protection for CEO-pending approvals with creator/submitter-safe access

## Dependencies

- `account`
- `mail`

## Recommended Pre-Publication Checks

Before publishing, verify the following in a staging environment:

- record-rule visibility for accountants, creators, submitters, approvers, auditors, and managers
- creator/submitter access to their own documents in Waiting CEO Approval and Waiting Auditor Approval
- branch approver visibility after documents move to CEO approval
- auditor-only approval and rejection for bills, invoices, and journal entries
- auditor activity creation after posting a bill, invoice, or manual journal entry that used a Branch/CEO route
- auditor approval completion and chatter message
- auditor rejection behavior and notification to the original user
- approval reset permissions before posting
- rejection and resubmission flow
- multi-company behavior and approver snapshot behavior after changing company approvers
- activity creation and cleanup
- posting restrictions under each route, including the restricted Not Required route
- search filters in customer invoice, vendor bill, and journal entry menus

## Roadmap Suggestions

Possible future enhancements:

- amount-based approval thresholds
- approval roles by branch, department, or analytic account
- delegated approvers / backup approvers
- escalation activities for overdue approvals
- dashboard reporting for pending approvals and pending audit reviews
- email templates for final approval, Auditor approval, and rejection

## Author

**HostKurd**

## License

See `LICENSE`.


### Upgrade note for Auditor version

This version adds new Python fields on `account.move` and `res.company`. Stop/restart the Odoo service before running the module upgrade so Odoo loads the new Python registry before validating XML/security domains.


### Schema safety fix

Version 19.0.5.0.2 adds defensive schema checks for the Auditor approval fields, including `res_company.account_approval_auditor_id`, to avoid 500 errors when new Python code is loaded before the database upgrade has fully created the new columns.

### Production hardening and Auditor Only route

Version 19.0.5.0.3 adds the **Auditor Only** route and hardens the approval workflow by protecting internal workflow fields, locking approved-but-unposted documents against material edits, restricting the **Not Required** bypass route, indexing approval search fields, and snapshotting approvers on submission.


### Ready-to-post invoice/bill posting fix

Version 19.0.5.0.4 fixes a posting issue where approved vendor bills and customer invoices could show **Ready to Post** but still raise “You cannot edit document details after submission or approval” when clicking **Confirm**. The edit lock remains active for normal user edits, but Odoo's internal accounting updates during posting are now allowed.


### Bill / invoice final-auditor routing and payment fix

Version 19.0.5.0.5 forwards posted vendor bills and customer invoices to the configured Auditor after Branch/CEO routes, not only manual journal entries. It also excludes Odoo-generated payment, bank-statement, exchange-difference, and cash-basis journal entries from the manual approval workflow so payment registration and reconciliation are not blocked by “must be approved before posting”. This version also adds the explicit Bill Approval Owner, Bill Approval Auditor, Invoice & Bill Accountant, and Bill Approval Branch Manager groups, including journal-item read access for approvers.

### Approval settings and non-bookkeeper approver access

Version 19.0.5.0.8 adds a dedicated **Settings > Accounting Approval** section, a global Auditor setting, optional reset-after-completion, optional Reset-to-Draft approval synchronization, and approval-only menus so Branch Managers, CEOs, and Auditors can review their assigned/approved/rejected documents without receiving the Bookkeeper permission or Accounting reports access.

### Approval-only Journal Items tab and edit lock

Version 19.0.5.0.10 adds a read-only Journal Items tab for Branch Managers, CEOs, and Auditors directly on vendor bills, vendor credit notes, customer invoices, customer credit notes, and journal entries. It also keeps those approval-only users read-only even if Odoo's basic **Invoicing** permission is assigned only to let them open accounting forms.


## 19.0.5.0.12

- Restricted Branch Manager / CEO / Auditor search visibility to accounting approval documents assigned to them.
- Added an extra Python-level visibility domain so standard Invoicing permission cannot expose all bills/invoices to approval-only users.
- Added a read-only **Assigned Journal Items** menu under Accounting Approval.
- Updated journal item record rules to follow the assigned approval document visibility.

## 19.0.5.0.13

- Added an **Assigned Journal Entries** action for Branch Managers, CEOs, and Auditors so manual journal entries assigned to them can be opened read-only without Bookkeeper permission.
- Added an **Approval** shortcut inside the Accounting app for users who still have Odoo's basic Invoicing group.
- Exposed **Assigned Journal Items** from the same Approval shortcut and added filters for Manual Journal Entries vs Bills / Invoices.

### Version 19.0.5.0.15

- Renamed the Odoo app launcher menu from Approval to Bill Approval.
- Added the module icon to the Bill Approval app launcher tile using the module static icon.



### Bill Approval app launcher name

Version 19.0.5.0.21 renames the launcher app and Accounting shortcut from **Approval** to **Bill Approval** to avoid confusion with Odoo's standard **Approvals** app. No workflow, security, settings, or view structure changes were made in this version.


## 19.0.5.0.22

Version 19.0.5.0.22 extends the approval workflow to vendor and customer credit notes (`in_refund` and `out_refund`), adds a guard for reversal auto-post paths, and adds the Product column to the approval-only Journal Items tab/menu for Branch Manager, CEO, and Auditor users.


## 19.0.5.0.23

Version 19.0.5.0.23 improves production behavior for reversals and approval-user visibility. **Reverse and Create Invoice** is now blocked earlier with a clear message for approval-controlled bills/invoices because it auto-posts the reversal credit note. Use **Reverse** instead so the credit note can pass the same approval workflow before posting. Branch Manager, CEO, and Auditor visibility was also tightened so default approver snapshots on draft/unsubmitted bills no longer make every bill visible; approval-only users now see documents where they are the current pending approver, previous approver/rejecter, creator, or submitter.

### Analytic column for approval-only Journal Items

Version 19.0.5.0.24 adds an **Analytic** column to the approval-only read-only Journal Items views. The value is shown through a safe read-only display field so Branch Manager, CEO, and Auditor users can review analytic distribution without needing full accounting edit permissions.

## 19.0.5.0.25

Version 19.0.5.0.25 renames the approval-only journal item column to **Analytic Distribution** and moves it after **Label**, before **Debit**, to match Odoo's native journal item layout.
