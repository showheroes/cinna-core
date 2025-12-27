# Vendor Bill Fields Documentation

This document describes the fields available for Vendor Bills (Odoo model: `account.move`, specifically with `move_type='in_invoice'`) that are exposed to the AI Assistant.

## Core Fields

These are the standard Odoo fields retrieved for vendor bills.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer | The unique database identifier for the bill. |
| `name` | String | The document number (e.g., BILL/2023/001). |
| `payment_reference` | String | The reference to be used in payment (often matches vendor's bill number). |
| `partner_id` | Many2one | The Vendor associated with this bill. Returns `[id, name]`. |
| `amount_total` | Float | The total amount of the bill including tax. |
| `amount_residual` | Float | The detail amount currently remaining to be paid. |
| `invoice_date` | Date | The date printed on the bill (YYYY-MM-DD). |
| `invoice_date_due` | Date | The date by which payment is expected (YYYY-MM-DD). |
| `state` | Selection | The status of the bill (e.g., `draft`, `posted`, `cancel`). |

## Custom Fields (Operations)

These fields are specifically added or used for the Billing Ops Assistant to track collection status.

### Dunning Status (`cf_dunning`)
**Type:** Selection
**Description:** Indicates the severity or stage of the dunning process for this specific bill.

**Allowed Values:**
- `friendly_reminder`: Initial polite reminder.
- `unfriendly_reminder`: Stronger reminder, no formal dunning yet.
- `dunning_1`: First formal dunning level.
- `dunning_2`: Second formal dunning level.
- `dunning_3`: Third formal dunning level.
- `deactivation_thread`: Warning that services will be maintained/stopped.
- `legal_threat`: Indication that legal action is threatened.

### Payment Comment (`cf_partner_payment_comment`)
**Type:** Text
**Description:** Internal notes or comments regarding the payment status, agent analysis, or agreements with the vendor.

## Partner Details
When expanded, the `partner_id` links to the `res.partner` model with the following available fields:
- `id`: Partner ID.
- `name`: Partner/Company name.
- `email`: Contact email.
- `phone`: Contact phone.
- `vat`: Tax Identification Number.
