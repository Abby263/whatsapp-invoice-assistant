
# AI Invoice Assistant: PostgreSQL Database Schema Design

## Overview
The **AI Invoice Assistant** is an application that allows users to interact via WhatsApp to upload invoices, receive AI-generated summaries, and ask questions about their invoices. The database must:
- Store user information and their interactions.
- Manage invoice metadata, line items, and associated media files.
- Track conversation history and WhatsApp-specific message data.
- Monitor API usage for analytics and billing.
- Ensure efficient querying and scalability.

This schema leverages PostgreSQL’s relational features, indexing, and JSON support to meet these needs.

---

## Database Tables and Keys

### 1. **Users Table**
- **Purpose**: Stores details of WhatsApp users interacting with the assistant.
- **Primary Key**: `id` (Integer, auto-increment)
- **Unique Constraints**: `whatsapp_number` (String, indexed)
- **Fields**:
  - `id`: Unique identifier for each user.
  - `whatsapp_number`: User’s WhatsApp number (e.g., "+1234567890").
  - `name`: User’s full name (nullable).
  - `email`: User’s email address (nullable).
  - `is_active`: Indicates if the user account is active (Boolean, default=true).
  - `created_at`: Timestamp of user creation.
  - `last_activity`: Timestamp of the user’s last interaction.
- **Relationships**:
  - One-to-many with `invoices`, `conversations`, `messages`, `media`, and `usage`.
- **Indexes**:
  - Unique index on `whatsapp_number` for fast lookups.
  - Index on `created_at` for sorting users by join date.

---

### 2. **Invoices Table**
- **Purpose**: Stores metadata and summaries of uploaded invoices.
- **Primary Key**: `id` (BigInteger, auto-increment)
- **Foreign Keys**: `user_id` references `users(id)`
- **Fields**:
  - `id`: Unique identifier for the invoice.
  - `user_id`: Links to the user who uploaded the invoice.
  - `invoice_number`: Invoice identifier (e.g., "INV-123").
  - `invoice_date`: Date the invoice was issued.
  - `vendor`: Name of the vendor or merchant.
  - `total_amount`: Total invoice amount (Float).
  - `tax_amount`: Tax portion of the invoice (Float, nullable).
  - `currency`: Currency code (e.g., "USD", default="USD").
  - `file_url`: URL to the stored invoice file.
  - `file_content_type`: MIME type (e.g., "application/pdf").
  - `raw_data`: JSON of extracted invoice data (Text, nullable).
  - `notes`: Additional user or system notes (Text, nullable).
  - `created_at`: Record creation timestamp.
  - `updated_at`: Record update timestamp.
- **Relationships**:
  - Many-to-one with `users`.
  - One-to-many with `items` and `media`.
- **Indexes**:
  - Index on `user_id` for user-specific queries.
  - Composite index on `invoice_date` and `vendor` for filtering.
  - Index on `total_amount` for range queries.

---

### 3. **Items Table**
- **Purpose**: Stores individual line items from invoices.
- **Primary Key**: `id` (Integer, auto-increment)
- **Foreign Keys**: `invoice_id` references `invoices(id)`
- **Fields**:
  - `id`: Unique identifier for the item.
  - `invoice_id`: Links to the parent invoice.
  - `description`: Item description (non-nullable).
  - `quantity`: Number of units (Float, default=1.0).
  - `unit_price`: Price per unit (Float, non-nullable).
  - `total_price`: Calculated as `quantity * unit_price` (Float, non-nullable).
  - `item_category`: Category (e.g., "Electronics", nullable).
  - `item_code`: SKU or product code (nullable).
  - `created_at`: Creation timestamp.
  - `updated_at`: Update timestamp.
- **Relationships**:
  - Many-to-one with `invoices`.
- **Indexes**:
  - Index on `invoice_id` for retrieving items by invoice.
  - Index on `item_category` for category-based analysis.

---

### 4. **Conversations Table**
- **Purpose**: Tracks conversation sessions between users and the AI.
- **Primary Key**: `id` (Integer, auto-increment)
- **Foreign Keys**: `user_id` references `users(id)`
- **Fields**:
  - `id`: Unique identifier for the conversation.
  - `user_id`: Links to the user.
  - `created_at`: Start timestamp of the conversation.
  - `updated_at`: Last update timestamp.
- **Relationships**:
  - Many-to-one with `users`.
  - One-to-many with `messages`.
- **Indexes**:
  - Index on `user_id` for user conversation history.
  - Index on `created_at` for chronological sorting.

---

### 5. **Messages Table**
- **Purpose**: Stores all messages in conversations (user, assistant, or system).
- **Primary Key**: `id` (Integer, auto-increment)
- **Foreign Keys**:
  - `user_id` references `users(id)`
  - `conversation_id` references `conversations(id)`
- **Fields**:
  - `id`: Unique identifier for the message.
  - `user_id`: Links to the user.
  - `conversation_id`: Links to the conversation.
  - `content`: Message text (non-nullable).
  - `role`: Sender type (Enum: "user", "assistant", "system").
  - `created_at`: Message creation timestamp.
- **Relationships**:
  - Many-to-one with `users` and `conversations`.
  - One-to-one with `whatsapp_messages`.
- **Indexes**:
  - Composite index on `conversation_id` and `created_at` for message ordering.

---

### 6. **WhatsAppMessages Table**
- **Purpose**: Stores WhatsApp-specific metadata for Twilio integration.
- **Primary Key**: `id` (Integer, auto-increment)
- **Foreign Keys**: `message_id` references `messages(id)`
- **Fields**:
  - `id`: Unique identifier.
  - `message_id`: Links to the corresponding message.
  - `whatsapp_message_id`: Twilio message ID (unique).
  - `from_number`: Sender’s WhatsApp number.
  - `to_number`: Recipient’s WhatsApp number.
  - `status`: Delivery status (Enum: "received", "sent", "delivered", "read", "failed").
  - `media_url`: URL to attached media (nullable).
  - `media_type`: Media MIME type (nullable).
  - `created_at`: Creation timestamp.
  - `updated_at`: Update timestamp.
- **Relationships**:
  - One-to-one with `messages`.
- **Indexes**:
  - Unique index on `whatsapp_message_id`.
  - Indexes on `from_number` and `to_number` for message tracking.

---

### 7. **Media Table**
- **Purpose**: Manages uploaded files (e.g., invoice PDFs/images) and their processing details.
- **Primary Key**: `id` (Integer, auto-increment)
- **Foreign Keys**:
  - `user_id` references `users(id)`
  - `invoice_id` references `invoices(id)` (nullable)
- **Fields**:
  - `id`: Unique identifier.
  - `user_id`: Links to the uploading user.
  - `invoice_id`: Links to the associated invoice (if processed).
  - `filename`: Storage-generated filename.
  - `original_filename`: User-provided filename (nullable).
  - `file_path`: Storage path (e.g., S3).
  - `file_url`: Public access URL.
  - `file_size`: Size in bytes (nullable).
  - `content_type`: MIME type (e.g., "image/jpeg").
  - `file_type`: Purpose (Enum: "invoice", "receipt", "attachment", "other").
  - `status`: Processing state (Enum: "uploaded", "processing", "processed", "failed").
  - `ocr_text`: Extracted text (Text, nullable).
  - `processing_metadata`: JSON of processing details (Text, nullable).
  - `created_at`: Creation timestamp.
  - `updated_at`: Update timestamp.
- **Relationships**:
  - Many-to-one with `users` and optionally `invoices`.
- **Indexes**:
  - Index on `user_id` for user media retrieval.
  - Index on `invoice_id` for invoice associations.
  - Index on `status` for processing monitoring.

---

### 8. **Usage Table**
- **Purpose**: Tracks LLM API usage for analytics and billing.
- **Primary Key**: `id` (Integer, auto-increment)
- **Foreign Keys**: `user_id` references `users(id)`
- **Fields**:
  - `id`: Unique identifier.
  - `user_id`: Links to the user.
  - `tokens_in`: Input tokens consumed (Integer, default=0).
  - `tokens_out`: Output tokens generated (Integer, default=0).
  - `usage_type`: API usage type (e.g., "chat").
  - `model_name`: LLM model used (e.g., "gpt-4", nullable).
  - `cost`: Estimated cost (Float, nullable).
  - `created_at`: Usage record timestamp.
- **Relationships**:
  - Many-to-one with `users`.
- **Indexes**:
  - Index on `user_id` for user usage reports.
  - Index on `created_at` for time-based analysis.

---

## Best Practices Applied

### 1. **Normalization**
- Tables like `users` and `invoices` are separated to avoid redundancy.
- `items` are split from `invoices` for efficient line-item management.

### 2. **Keys and Relationships**
- Primary keys (`id`) ensure unique records.
- Foreign keys (e.g., `user_id`, `invoice_id`) enforce referential integrity and are indexed for performance.

### 3. **Indexing**
- Unique indexes (e.g., `whatsapp_number`) ensure data uniqueness.
- Composite indexes (e.g., `invoice_date` and `vendor`) optimize common queries.
- Foreign key indexes improve join performance.

### 4. **Data Types**
- Enums (e.g., `role`, `status`) enforce valid values.
- JSON fields (e.g., `raw_data`) store unstructured data flexibly.

### 5. **Timestamps**
- `created_at` and `updated_at` track record history, with indexes where sorting is needed.

### 6. **Scalability**
- `BigInteger` for `invoices.id` supports high record volumes.
- Partitioning can be added for `messages` or `usage` in large-scale scenarios.

### 7. **Security**
- Nullable fields (e.g., `email`) avoid storing unnecessary PII.
- Sensitive data access should be controlled at the application level.

### 8. **Maintainability**
- Use a migration tool like **Alembic** to manage schema changes, with a dedicated `alembic_version` table.

---

## Conclusion
This PostgreSQL schema supports the **AI Invoice Assistant** by providing a robust, scalable, and efficient structure for managing users, invoices, conversations, media, and usage data. By adhering to best practices—normalization, indexing, and appropriate data types—it’s ready for production deployment and future enhancements like advanced analytics or third-party integrations.