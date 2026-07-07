# Customer Support Ticket API Reference

## Overview

The Customer Support Ticket API provides endpoints to manage support tickets, including creation, retrieval, updates, and automatic classification using AI. All timestamps are in ISO 8601 format, and ticket IDs are UUIDs.

**Base URL:** `http://localhost:8000`

**Content-Type:** `application/json` (except where noted)

---

## Endpoints

### Health Check

#### GET /

**Description:** Returns the API status and service information.

**Parameters:** None

**Request Body:** None

**Success Response (200):**
```json
{
  "service": "Customer Support Ticket API",
  "status": "ok"
}
```

**cURL:**
```bash
curl -X GET http://localhost:8000/
```

**Status Codes:**
- `200 OK` — Service is healthy

---

### Create Ticket

#### POST /tickets

**Description:** Creates a new support ticket. Optionally runs automatic classification on the ticket.

**Query Parameters:**
- `auto_classify` (boolean, optional, default: false) — If true, automatically classifies the ticket into a category and priority level.

**Request Body:**
```json
{
  "customer_id": "CUST-1001",
  "customer_email": "jane@example.com",
  "customer_name": "Jane Doe",
  "subject": "Cannot log in",
  "description": "I reset my password but I still cannot access my account.",
  "category": "account_access",
  "priority": "high",
  "status": "new",
  "assigned_to": null,
  "tags": ["login", "access"],
  "metadata": {
    "source": "web_form",
    "browser": "Chrome",
    "device_type": "desktop"
  }
}
```

**Success Response (201):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "customer_id": "CUST-1001",
  "customer_email": "jane@example.com",
  "customer_name": "Jane Doe",
  "subject": "Cannot log in",
  "description": "I reset my password but I still cannot access my account.",
  "category": "account_access",
  "priority": "high",
  "status": "new",
  "assigned_to": null,
  "tags": ["login", "access"],
  "metadata": {
    "source": "web_form",
    "browser": "Chrome",
    "device_type": "desktop"
  },
  "created_at": "2026-07-07T10:30:00Z",
  "updated_at": "2026-07-07T10:30:00Z",
  "resolved_at": null,
  "classification": null
}
```

**cURL:**
```bash
curl -X POST http://localhost:8000/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "CUST-1001",
    "customer_email": "jane@example.com",
    "customer_name": "Jane Doe",
    "subject": "Cannot log in",
    "description": "I reset my password but I still cannot access my account.",
    "tags": ["login", "access"],
    "metadata": {
      "source": "web_form",
      "browser": "Chrome",
      "device_type": "desktop"
    }
  }'
```

**cURL with auto-classification:**
```bash
curl -X POST "http://localhost:8000/tickets?auto_classify=true" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "CUST-1001",
    "customer_email": "jane@example.com",
    "customer_name": "Jane Doe",
    "subject": "Cannot log in",
    "description": "I reset my password but I still cannot access my account.",
    "tags": ["login", "access"],
    "metadata": {
      "source": "web_form",
      "browser": "Chrome",
      "device_type": "desktop"
    }
  }'
```

**Status Codes:**
- `201 Created` — Ticket successfully created
- `400 Bad Request` — Validation failed

---

### List Tickets

#### GET /tickets

**Description:** Retrieves a list of tickets with optional filtering.

**Query Parameters (all optional, combinable):**
- `category` (string) — Filter by category (e.g., `account_access`, `technical_issue`, `bug_report`)
- `priority` (string) — Filter by priority (e.g., `urgent`, `high`, `medium`, `low`)
- `status` (string) — Filter by status (e.g., `new`, `in_progress`, `resolved`, `closed`)
- `assigned_to` (string) — Filter by assigned agent
- `customer_id` (string) — Filter by customer ID
- `tag` (string) — Filter by tag (tickets must contain this tag)

**Request Body:** None

**Success Response (200):**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "customer_id": "CUST-1001",
    "customer_email": "jane@example.com",
    "customer_name": "Jane Doe",
    "subject": "Cannot log in",
    "description": "I reset my password but I still cannot access my account.",
    "category": "account_access",
    "priority": "high",
    "status": "new",
    "assigned_to": null,
    "tags": ["login", "access"],
    "metadata": {
      "source": "web_form",
      "browser": "Chrome",
      "device_type": "desktop"
    },
    "created_at": "2026-07-07T10:30:00Z",
    "updated_at": "2026-07-07T10:30:00Z",
    "resolved_at": null,
    "classification": null
  }
]
```

**cURL:**
```bash
curl -X GET "http://localhost:8000/tickets"
```

**cURL with filters:**
```bash
curl -X GET "http://localhost:8000/tickets?status=new&priority=high&category=account_access"
```

**cURL filter by customer:**
```bash
curl -X GET "http://localhost:8000/tickets?customer_id=CUST-1001"
```

**cURL filter by tag:**
```bash
curl -X GET "http://localhost:8000/tickets?tag=login"
```

**Status Codes:**
- `200 OK` — List retrieved successfully (may be empty)

---

### Get Ticket by ID

#### GET /tickets/{id}

**Description:** Retrieves a single ticket by its UUID.

**Path Parameters:**
- `id` (string, required) — Ticket UUID

**Query Parameters:** None

**Request Body:** None

**Success Response (200):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "customer_id": "CUST-1001",
  "customer_email": "jane@example.com",
  "customer_name": "Jane Doe",
  "subject": "Cannot log in",
  "description": "I reset my password but I still cannot access my account.",
  "category": "account_access",
  "priority": "high",
  "status": "new",
  "assigned_to": null,
  "tags": ["login", "access"],
  "metadata": {
    "source": "web_form",
    "browser": "Chrome",
    "device_type": "desktop"
  },
  "created_at": "2026-07-07T10:30:00Z",
  "updated_at": "2026-07-07T10:30:00Z",
  "resolved_at": null,
  "classification": null
}
```

**cURL:**
```bash
curl -X GET http://localhost:8000/tickets/550e8400-e29b-41d4-a716-446655440000
```

**Status Codes:**
- `200 OK` — Ticket found
- `404 Not Found` — Ticket does not exist

---

### Update Ticket

#### PUT /tickets/{id}

**Description:** Partially updates an existing ticket. Any subset of fields can be provided. The `updated_at` timestamp is automatically updated. When `status` is changed to `resolved` or `closed`, the `resolved_at` field is automatically set.

**Path Parameters:**
- `id` (string, required) — Ticket UUID

**Query Parameters:** None

**Request Body (all fields optional):**
```json
{
  "status": "in_progress",
  "priority": "urgent",
  "assigned_to": "agent_smith",
  "tags": ["login", "access", "urgent"],
  "category": "account_access"
}
```

**Success Response (200):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "customer_id": "CUST-1001",
  "customer_email": "jane@example.com",
  "customer_name": "Jane Doe",
  "subject": "Cannot log in",
  "description": "I reset my password but I still cannot access my account.",
  "category": "account_access",
  "priority": "urgent",
  "status": "in_progress",
  "assigned_to": "agent_smith",
  "tags": ["login", "access", "urgent"],
  "metadata": {
    "source": "web_form",
    "browser": "Chrome",
    "device_type": "desktop"
  },
  "created_at": "2026-07-07T10:30:00Z",
  "updated_at": "2026-07-07T10:35:00Z",
  "resolved_at": null,
  "classification": null
}
```

**cURL:**
```bash
curl -X PUT http://localhost:8000/tickets/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -d '{
    "status": "in_progress",
    "priority": "urgent",
    "assigned_to": "agent_smith"
  }'
```

**cURL resolving a ticket:**
```bash
curl -X PUT http://localhost:8000/tickets/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -d '{
    "status": "resolved"
  }'
```

**Status Codes:**
- `200 OK` — Ticket successfully updated
- `404 Not Found` — Ticket does not exist
- `400 Bad Request` — Validation failed

---

### Delete Ticket

#### DELETE /tickets/{id}

**Description:** Permanently deletes a ticket.

**Path Parameters:**
- `id` (string, required) — Ticket UUID

**Query Parameters:** None

**Request Body:** None

**Success Response (204):** No content

**cURL:**
```bash
curl -X DELETE http://localhost:8000/tickets/550e8400-e29b-41d4-a716-446655440000
```

**Status Codes:**
- `204 No Content` — Ticket successfully deleted
- `404 Not Found` — Ticket does not exist

---

### Auto-Classify Ticket

#### POST /tickets/{id}/auto-classify

**Description:** Runs the AI classifier on an existing ticket to automatically determine its category and priority based on the subject and description. Returns classification metadata including confidence and reasoning.

**Path Parameters:**
- `id` (string, required) — Ticket UUID

**Query Parameters:** None

**Request Body:** None

**Success Response (200):**
```json
{
  "category": "account_access",
  "priority": "high",
  "confidence": 0.92,
  "reasoning": "Ticket mentions password reset failure and account access denial, indicating an account access issue.",
  "keywords": ["password", "reset", "cannot access", "login", "account"]
}
```

**cURL:**
```bash
curl -X POST http://localhost:8000/tickets/550e8400-e29b-41d4-a716-446655440000/auto-classify
```

**Status Codes:**
- `200 OK` — Classification completed successfully
- `404 Not Found` — Ticket does not exist

---

### Import Tickets

#### POST /tickets/import

**Description:** Bulk imports tickets from a file (CSV, JSON, or XML). Optionally auto-classifies each imported ticket. Returns a summary of the import operation including counts of successful and failed imports.

**Query Parameters:**
- `format` (string, optional) — File format: `csv`, `json`, or `xml`. If omitted, inferred from the file extension.
- `auto_classify` (boolean, optional, default: false) — If true, automatically classifies each imported ticket.

**Request Body:** Multipart form data
- `file` (file, required) — The import file

**Success Response (200):**
```json
{
  "total": 3,
  "successful": 2,
  "failed": 1,
  "errors": [
    {
      "index": 1,
      "errors": ["description: too short (minimum 10 characters)"]
    }
  ],
  "created_ids": [
    "550e8400-e29b-41d4-a716-446655440001",
    "550e8400-e29b-41d4-a716-446655440002"
  ]
}
```

**cURL (CSV):**
```bash
curl -X POST "http://localhost:8000/tickets/import?format=csv" \
  -F "file=@demo/sample_tickets.csv"
```

**cURL (JSON with auto-classification):**
```bash
curl -X POST "http://localhost:8000/tickets/import?format=json&auto_classify=true" \
  -F "file=@tickets.json"
```

**cURL (format auto-detected from filename):**
```bash
curl -X POST "http://localhost:8000/tickets/import" \
  -F "file=@tickets.xml"
```

**Error Response (400):**
```json
{
  "error": "Import failed",
  "message": "Malformed XML: expected closing tag 'ticket' at line 5"
}
```

**Status Codes:**
- `200 OK` — Import completed (check the response for partial success)
- `400 Bad Request` — File format is invalid or malformed

---

## Data Models

### Ticket

The Ticket object represents a single support ticket.

| Field | Type | Description |
|-------|------|-------------|
| `id` | string (UUID) | Unique identifier for the ticket. Auto-generated on creation. |
| `customer_id` | string | Identifier for the customer who created the ticket. |
| `customer_email` | string (email) | Email address of the customer. |
| `customer_name` | string | Name of the customer. |
| `subject` | string | Ticket subject (1–200 characters). |
| `description` | string | Detailed ticket description (10–2000 characters). |
| `category` | string (enum) | Ticket category. See Category enum. Default: `other`. |
| `priority` | string (enum) | Ticket priority level. See Priority enum. Default: `medium`. |
| `status` | string (enum) | Ticket status. See Status enum. Default: `new`. |
| `assigned_to` | string or null | Username or ID of the assigned support agent. Null if unassigned. |
| `tags` | array of strings | Array of tags for organizing and filtering tickets. |
| `metadata` | Metadata object or null | Additional context about the ticket source and device. |
| `created_at` | string (ISO 8601) | Timestamp when the ticket was created. |
| `updated_at` | string (ISO 8601) | Timestamp when the ticket was last updated. |
| `resolved_at` | string (ISO 8601) or null | Timestamp when the ticket was resolved or closed. Null if not yet resolved. |
| `classification` | object or null | AI classification result (when auto-classify is used). Contains `category`, `priority`, `confidence`, and `reasoning`. |

### Metadata

Additional context about the ticket's source and environment.

| Field | Type | Description |
|-------|------|-------------|
| `source` | string (enum) | Channel through which the ticket was submitted. See Metadata Source enum. |
| `browser` | string | Browser name (e.g., "Chrome", "Firefox", "Safari"). Optional. |
| `device_type` | string (enum) | Type of device used. See Metadata Device Type enum. |

### Enums

#### Category

Available ticket categories:

- `account_access` — Login, password, or account access issues
- `technical_issue` — Technical problems or system errors
- `billing_question` — Questions about billing, invoicing, or pricing
- `feature_request` — Requests for new features or enhancements
- `bug_report` — Reports of bugs or unexpected behavior
- `other` — General or miscellaneous issues

#### Priority

Available priority levels:

- `urgent` — Requires immediate attention
- `high` — Should be addressed soon
- `medium` — Standard priority (default)
- `low` — Can be addressed when time permits

#### Status

Available ticket statuses:

- `new` — Newly created, not yet assigned or reviewed
- `in_progress` — Being actively worked on
- `waiting_customer` — Waiting for customer response or information
- `resolved` — Issue has been resolved
- `closed` — Ticket is closed and no longer active

#### Metadata Source

Channels through which a ticket was submitted:

- `web_form` — Submitted via web form
- `email` — Received via email
- `api` — Created via API
- `chat` — Submitted via chat interface
- `phone` — Created from phone conversation

#### Metadata Device Type

Device types:

- `desktop` — Desktop or laptop computer
- `mobile` — Mobile phone
- `tablet` — Tablet device

---

## Error Responses

### Validation Error (400)

Returned when the request body fails validation.

**Response:**
```json
{
  "error": "Validation failed",
  "details": [
    {
      "field": "subject",
      "message": "subject must be between 1 and 200 characters"
    },
    {
      "field": "description",
      "message": "description must be between 10 and 2000 characters"
    },
    {
      "field": "customer_email",
      "message": "customer_email must be a valid email address"
    }
  ]
}
```

### Not Found (404)

Returned when a ticket with the specified ID does not exist.

**Response:**
```json
{
  "error": "Not found",
  "message": "Ticket with id '550e8400-e29b-41d4-a716-446655440000' not found"
}
```

### Import Error (400)

Returned when an import file is malformed or cannot be processed.

**Response:**
```json
{
  "error": "Import failed",
  "message": "CSV parsing error: unexpected number of columns at row 3"
}
```

---

## Best Practices

1. **Always validate input:** Ensure customer email, subject, and description meet length and format requirements before submitting.
2. **Use auto-classification:** When creating or importing tickets at scale, use the `auto_classify` flag to reduce manual categorization work.
3. **Filter efficiently:** Use query parameters when listing tickets to retrieve only relevant tickets and reduce response size.
4. **Handle status changes:** Remember that changing status to `resolved` or `closed` automatically sets `resolved_at`.
5. **Partial updates:** Use PUT requests with only the fields you want to change to avoid accidental overwrites.
6. **Bulk operations:** For large numbers of tickets, use the import endpoint rather than individual create requests.
