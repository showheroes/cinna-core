# Odoo Connection & Integration Guide

This document provides guidelines for integrating with Odoo, specifically tailored for LLMs and developers building workflows within this project. It outlines the standard connection methods, architectural patterns for separation of concerns, and best practices for efficient data handling.

## 1. Connection Method (XML-RPC)

Odoo matches the standard [External API](https://www.odoo.com/documentation/master/developer/reference/external_api.html) specifications using XML-RPC.

### Credentials
Connection requires four standard parameters, typically loaded from environment variables (`.env`):
- `URL`: The base URL of the Odoo instance (e.g., `https://my-odoo-instance.com`).
- `DB`: The database name.
- `USERNAME`: The user's login email.
- `PASSWORD`: The user's API key (preferred) or password.

### core endpoints
Authentication and interaction happen via two main endpoints:
1.  `common`: Used for authentication (`authenticate`). Returns a User ID (`uid`).
2.  `object`: Used for calling methods on models (`execute_kw`).

## 2. Architecture: Separation of Concerns

To maintain clean code and testability, we **do not** write raw XML-RPC calls directly inside business logic scripts. Instead, we rigidly encapsulate all Odoo interactions within a dedicated client class.

### The `OdooClient` Pattern
- **Location**: Implement a dedicated wrapper, typically `core/odoo_client.py` (or similar depending on the specific service).
- **Responsibility**: This class handles authentication, error logging, and standardizing return formats.
- **Abstraction**: Business scripts should call semantic methods like `search_invoices_by_reference(...)` rather than raw `execute_kw(...)` calls.

**Example Structure:**
```python
class OdooClient:
    def __init__(self, env_path):
        # Load credentials
        pass

    def connect(self):
        # Handle XML-RPC authentication
        pass
        
    def specific_business_method(self, arg1):
        # Wrapper around execute_kw
        # Handle exceptions and logging here
        pass
```

## 3. Best Practices

### Batch Processing
When processing large datasets (e.g., downloading thousands of records), **never** fetch all records in a single call.
- **Why**: Prevents memory overflows and timeouts.
- **How**: Fetch records in chunks (e.g., 500 or 1000 records at a time) using the `limit` and `offset` parameters in your search.

### Deterministic Ordering (Critical)
When using batch processing (pagination), you **MUST** provide a deterministic `order` parameter.
- **Risk**: If you don't specify an order, Odoo's default sorting might trigger inconsistent results between batches, causing you to process duplicate records or skip records entirely.
- **Solution**: Always sort by ID (e.g., `order='id asc'`) or another unique field when paginating.

### Active vs. Archived Records
By default, Odoo's `search` method **only returns active records** (`active=True`).
- **Standard**: If you need to find *all* records (including archived ones), you must explicitly add `['active', 'in', [True, False]]` to your search domain.
- **Context**: Always verify if the business logic requires historical (archived) data or just current operational data.

### Multi-Company Awareness
Odoo is intrinsically a multi-company environment.
- **Visibility**: The API user's access is restricted to their allowed companies. You may not see records from other companies even if they exist in the database.
- **Clarity**: It is vital to be clear about which company context the script is running in. Records (like Invoices, Journals) are often company-specific (`company_id`).
- **Best Practice**: If the user has access to multiple companies, ensure your queries are targeting the intended company scope. Conflicting company IDs in relational fields (e.g., trying to link a Company A invoice to a Company B journal) will raise access errors.

### Field Selection
Always specify the `fields` parameter in `read` calls.
- **Why**: Retrieving all fields for a model is slow and bandwidth-heavy.
- **How**: Only request the exact fields validation or logic requires.

## 4. Example Domain Logic (Many2One Searching)
Searching across relational fields (like finding a bill by a partner's name) requires specific domain syntax.
- **Syntax**: `['field_name.sub_field', 'operator', value]`
- **Example**: `['partner_id.name', 'ilike', 'Google']` will search for invoices where the linked partner's name contains "Google".

## 5. Error Handling
- The `OdooClient` should catch `xmlrpc.client.Fault` or generic `Exception`.
- Errors should be logged with context (e.g., "Failed to update invoice ID 123") rather than crashing the entire workflow.
- Return `False`, `None`, or empty lists `[]` on failure to allow the calling script to handle the flow gracefully.
