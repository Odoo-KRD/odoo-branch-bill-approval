# Branch Bill Approval

## Overview

**Branch Bill Approval** adds a controlled approval workflow for vendor bills in **Odoo 19**.

Before a vendor bill can be posted, the module can require approval based on one of the following routes:

- **Not Required**
- **Branch Only**
- **Branch then CEO**
- **CEO Only**

This helps organizations enforce internal controls, reduce unauthorized posting, and maintain a clear audit trail for bill approvals.

## Key Features

- Approval route selection directly on vendor bills
- Configurable company-level approvers
- Branch-only approval flow
- Two-step Branch then CEO approval flow
- CEO-only approval flow
- Rejection with mandatory reason
- Automatic posting restriction until required approvals are completed
- Approval activity scheduling for approvers
- Approval tracking fields for submission, approval, and rejection history
- Chatter logging for major approval actions

## Approval Routes

### Not Required
The vendor bill does not require approval and can be posted normally.

### Branch Only
The vendor bill must be approved by the configured **Branch Bill Approver**.

### Branch then CEO
The vendor bill must first be approved by the **Branch Bill Approver**, then by the **CEO Bill Approver**.

### CEO Only
The vendor bill is routed directly to the **CEO Bill Approver**.

## Installation

1. Copy the module into your Odoo custom addons path.
2. Update the apps list.
3. Install **Branch Bill Approval** from the Apps menu.

## Configuration

Go to **Settings / Companies**, open the target company, and configure:

- **Branch Bill Approver**
- **CEO Bill Approver**

These approvers are used automatically according to the selected route on the vendor bill.

## Usage

1. Create a vendor bill.
2. Select the appropriate **Approval Route**.
3. Click **Submit for Approval**.
4. The assigned approver receives an activity.
5. The approver can:
   - **Approve** the bill
   - **Reject** the bill with a reason
6. Once the required approval flow is completed, the bill can be posted.

## Functional Notes

- The workflow applies only to **vendor bills**.
- Bills with **Not Required** as the approval route do not need submission.
- Bills in approval cannot be posted until the required route is fully approved.
- Key bill fields are protected while approval is in progress.
- Rejected bills keep the rejection reason for audit purposes.

## Technical Summary

The module extends `account.move` to add:

- approval route selection
- approval state tracking
- approver assignment from company settings
- submission and approval audit fields
- rejection wizard integration
- activity scheduling for approvers
- posting validation before final approval

## Dependencies

- `account`
- `mail`

## Included Files

- company approver configuration views
- vendor bill approval UI
- rejection wizard
- security groups and rules
- automated tests for the main approval routes

## Recommended Pre-Publication Checks

Before publishing, verify the following in a staging environment:

- record-rule visibility for accountants, approvers, and managers
- approval reset permissions
- rejection and resubmission flow
- multi-company behavior
- activity creation and cleanup
- posting restrictions under each route

## Roadmap

Possible future enhancements:

- configurable approval roles by branch or department
- amount-based approval thresholds
- approval delegation and backup approvers
- richer audit reporting
- improved security-role separation

## Support

For support, customizations, or implementation services, add your company support email or website here.

## Author

**HostKurd**

## License

**MIT**
