# AI Invoice Assistant: PostgreSQL Database Schema Design

## Overview
The **AI Invoice Assistant** is an application that allows users to interact via WhatsApp to upload invoices, receive AI-generated summaries, and ask questions about their invoices. The database must:
- Store user information and their interactions.
- Manage invoice metadata, line items, and associated media files.
- Track conversation history and WhatsApp-specific message data.
- Monitor API usage for analytics and billing.
- Store and query vector embeddings for semantic search capabilities.
- Ensure efficient querying and scalability.

This schema leverages PostgreSQL's relational features, indexing, JSON support, and pgvector extension to meet these needs.

---

## Validated Environment

The database environment has been validated with:
- PostgreSQL 14.17
- pgvector extension version 0.8.0
- 9 defined tables with proper relationships
- Vector embeddings for semantic search capability

```sql
-- Confirming pgvector extension
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
 extname | extversion 
---------+------------
 vector  | 0.8.0
```

---

## Database Tables and Keys

### 1. **Users Table**
- **Purpose**: Stores details of WhatsApp users interacting with the assistant.
- **Primary Key**: `id` (Integer, auto-increment)
- **Unique Constraints**: `whatsapp_number` (String, indexed)
- **Fields**:
  - `id`: Unique identifier for each user.
  - `whatsapp_number`: User's WhatsApp number (e.g., "+1234567890").
  - `name`: User's full name (nullable).
  - `email`: User's email address (nullable).
  - `is_active`: Indicates if the user account is active (Boolean).
  - `created_at`: Timestamp of user creation.
  - `updated_at`: Timestamp of last update.
- **Relationships**:
  - One-to-many with `invoices`, `conversations`, `messages`, `media`, `usage`, and `invoice_embeddings`.
- **Indexes**:
  - Unique index on `whatsapp_number` for fast lookups.

**Validation Results**:
```sql
TABLE "public.users"
     Column      |            Type             | Collation | Nullable |              Default              
-----------------+-----------------------------+-----------+----------+-----------------------------------
 id              | integer                     |           | not null | nextval('users_id_seq'::regclass)
 whatsapp_number | character varying(20)       |           | not null | 
 name            | character varying(100)      |           |          | 
 email           | character varying(100)      |           |          | 
 created_at      | timestamp without time zone |           |          | 
 updated_at      | timestamp without time zone |           |          | 
 is_active       | boolean                     |           |          | 
```

---

### 2. **Invoices Table**
- **Purpose**: Stores metadata and summaries of uploaded invoices.
- **Primary Key**: `id` (Integer, auto-increment)
- **Foreign Keys**: `user_id` references `users(id)`
- **Fields**:
  - `id`: Unique identifier for the invoice.
  - `user_id`: Links to the user who uploaded the invoice.
  - `invoice_number`: Invoice identifier (e.g., "INV-123").
  - `invoice_date`: Date the invoice was issued.
  - `vendor`: Name of the vendor or merchant.
  - `total_amount`: Total invoice amount (Float).
  - `tax_amount`: Tax portion of the invoice (Float, nullable).
  - `currency`: Currency code (e.g., "USD").
  - `file_url`: URL to the stored invoice file.
  - `file_content_type`: MIME type (e.g., "application/pdf").
  - `raw_data`: JSON of extracted invoice data.
  - `notes`: Additional user or system notes.
  - `created_at`: Record creation timestamp.
  - `updated_at`: Record update timestamp.
- **Relationships**:
  - Many-to-one with `users`.
  - One-to-many with `items`, `media`, and `invoice_embeddings`.

**Validation Results**:
```sql
TABLE "public.invoices"
      Column       |            Type             | Collation | Nullable |               Default
-------------------+-----------------------------+-----------+----------+-------------------------------------
 id                | integer                     |           | not null | nextval('invoices_id_seq'::regclass)
 user_id           | integer                     |           |          | 
 invoice_number    | character varying(50)       |           |          | 
 invoice_date      | timestamp without time zone |           |          | 
 vendor            | character varying(100)      |           |          | 
 total_amount      | double precision            |           |          | 
 tax_amount        | double precision            |           |          | 
 currency          | character varying(3)        |           |          | 
 file_url          | character varying(255)      |           |          | 
 file_content_type | character varying(50)       |           |          | 
 raw_data          | json                        |           |          | 
 notes             | text                        |           |          | 
 created_at        | timestamp without time zone |           |          | 
 updated_at        | timestamp without time zone |           |          | 
```

Current Data Summary:
- 5 invoices currently in the database
- 1 user with associated invoices

---

### 3. **Items Table**
- **Purpose**: Stores individual line items from invoices.
- **Primary Key**: `id` (Integer, auto-increment)
- **Foreign Keys**: `invoice_id` references `invoices(id)`
- **Fields**:
  - `id`: Unique identifier for the item.
  - `invoice_id`: Links to the parent invoice.
  - `description`: Item description (non-nullable).
  - `quantity`: Number of units (Float).
  - `unit_price`: Price per unit (Float, non-nullable).
  - `total_price`: Calculated as `quantity * unit_price` (Float, non-nullable).
  - `item_category`: Category (e.g., "Electronics", nullable).
  - `item_code`: SKU or product code (nullable).
  - `description_embedding`: Vector embedding for semantic search (vector(1536)).
  - `created_at`: Creation timestamp.
  - `updated_at`: Update timestamp.
- **Relationships**:
  - Many-to-one with `invoices`.
- **Indexes**:
  - Index on `invoice_id` for retrieving items by invoice.
  - Index on `item_category` for category-based analysis.

**Validation Results**:
```sql
TABLE "public.items"
        Column         |            Type             | Collation | Nullable |              Default
-----------------------+-----------------------------+-----------+----------+-----------------------------------
 id                    | integer                     |           | not null | nextval('items_id_seq'::regclass)
 invoice_id            | integer                     |           |          | 
 description           | character varying(255)      |           | not null | 
 quantity              | double precision            |           |          | 
 unit_price            | double precision            |           | not null | 
 total_price           | double precision            |           | not null | 
 item_category         | character varying(50)       |           |          | 
 item_code             | character varying(50)       |           |          | 
 description_embedding | vector(1536)                |           |          | 
 created_at            | timestamp without time zone |           |          | 
 updated_at            | timestamp without time zone |           |          | 
```

Current Data Summary:
- 28 items in the database
- All 28 items have vector embeddings
- Each item has a 1536-dimensional vector for semantic search

---

### 4. **Invoice Embeddings Table**
- **Purpose**: Stores vector embeddings for full invoice text, enabling semantic search across entire documents.
- **Primary Key**: `id` (Integer, auto-increment)
- **Foreign Keys**: 
  - `invoice_id` references `invoices(id)`
  - `user_id` references `users(id)`
- **Fields**:
  - `id`: Unique identifier.
  - `invoice_id`: Links to the associated invoice.
  - `user_id`: Links to the owning user.
  - `content_text`: Original text content used to generate the embedding.
  - `embedding`: Vector embedding (vector(1536)).
  - `model_name`: Name of the embedding model used (e.g., "text-embedding-3-small").
  - `embedding_type`: Type of embedding (e.g., "full_text", "summary").
  - `created_at`: Creation timestamp.
  - `updated_at`: Update timestamp.
- **Relationships**:
  - Many-to-one with `invoices` and `users`.
- **Constraints**:
  - Unique constraint on `(invoice_id, embedding_type)` to prevent duplicates.

**Validation Results**:
```sql
TABLE "public.invoice_embeddings"
     Column     |            Type             | Collation | Nullable |                    Default
----------------+-----------------------------+-----------+----------+---------------------------------------
 id             | integer                     |           | not null | nextval('invoice_embeddings_id_seq'::regclass)
 invoice_id     | integer                     |           | not null | 
 user_id        | integer                     |           | not null | 
 content_text   | text                        |           |          | 
 embedding      | vector(1536)                |           |          | 
 model_name     | character varying(100)      |           |          | 
 embedding_type | character varying(50)       |           |          | 
 created_at     | timestamp without time zone |           |          | 
 updated_at     | timestamp without time zone |           |          | 
```

---

### 5. **Conversations Table**
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

Current Data Summary:
- No conversations in the database yet

---

### 6. **Messages Table**
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

Current Data Summary:
- No messages in the database yet

---

### 7. **WhatsAppMessages Table**
- **Purpose**: Stores WhatsApp-specific metadata for Twilio integration.
- **Primary Key**: `id` (Integer, auto-increment)
- **Foreign Keys**: `message_id` references `messages(id)`
- **Fields**:
  - `id`: Unique identifier.
  - `message_id`: Links to the corresponding message.
  - `whatsapp_message_id`: Twilio message ID (unique).
  - `from_number`: Sender's WhatsApp number.
  - `to_number`: Recipient's WhatsApp number.
  - `status`: Delivery status (Enum: "received", "sent", "delivered", "read", "failed").
  - `media_url`: URL to attached media (nullable).
  - `media_type`: Media MIME type (nullable).
  - `created_at`: Creation timestamp.
  - `updated_at`: Update timestamp.
- **Relationships**:
  - One-to-one with `messages`.

---

### 8. **Media Table**
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

---

### 9. **Usage Table**
- **Purpose**: Tracks LLM API usage for analytics and billing.
- **Primary Key**: `id` (Integer, auto-increment)
- **Foreign Keys**: `user_id` references `users(id)`
- **Fields**:
  - `id`: Unique identifier.
  - `user_id`: Links to the user.
  - `tokens_in`: Input tokens consumed (Integer, default=0).
  - `tokens_out`: Output tokens generated (Integer, default=0).
  - `usage_type`: API usage type (e.g., "chat").
  - `model_name`: LLM model used (e.g., "gpt-4o-mini", nullable).
  - `cost`: Estimated cost (Float, nullable).
  - `created_at`: Usage record timestamp.
- **Relationships**:
  - Many-to-one with `users`.

---

## Vector Search Implementation

The WhatsApp Invoice Assistant uses pgvector to implement semantic search capabilities:

### 1. Vector Data Types
- Both `items.description_embedding` and `invoice_embeddings.embedding` use the `vector(1536)` data type provided by pgvector
- The dimension size (1536) matches OpenAI's text-embedding-3-small model output

### 2. Vector Generation
- All 28 items in the database have embeddings generated
- Embeddings are stored in an optimized format for similarity search

### 3. Semantic Search Support
- The pgvector extension enables several distance metrics for similarity search:
  - L2 distance (Euclidean)
  - Cosine similarity
  - Inner product

### 4. Sample Query for Semantic Search
```sql
-- Find semantically similar items to a query embedding
SELECT 
    description,
    l2_distance(description_embedding, $1) as similarity_score
FROM 
    items
WHERE 
    l2_distance(description_embedding, $1) < 1.3
ORDER BY 
    similarity_score
LIMIT 10;
```

### 5. Indexed Search with IVF
While not currently implemented, for larger datasets we recommend:
```sql
-- Create an IVFFlat index for faster vector similarity search
CREATE INDEX items_embedding_idx ON items 
USING ivfflat (description_embedding vector_l2_ops)
WITH (lists = 100);
```

---

## Best Practices Applied

### 1. **Normalization**
- Tables like `users` and `invoices` are separated to avoid redundancy.
- `items` are split from `invoices` for efficient line-item management.
- `invoice_embeddings` separates vector data from the main invoice table for better performance.

### 2. **Keys and Relationships**
- Primary keys (`id`) ensure unique records.
- Foreign keys (e.g., `user_id`, `invoice_id`) enforce referential integrity and are indexed for performance.
- Unique constraint on `(invoice_id, embedding_type)` prevents duplicate embeddings.

### 3. **Indexing**
- Unique indexes (e.g., `whatsapp_number`) ensure data uniqueness.
- Foreign key indexes improve join performance.
- Vector indexing (via pgvector) enables efficient similarity search.

### 4. **Data Types**
- Vector type from pgvector extension for embeddings.
- JSON fields (e.g., `raw_data`) store unstructured data flexibly.

### 5. **Timestamps**
- `created_at` and `updated_at` track record history, with indexes where sorting is needed.

### 6. **Scalability**
- pgvector's IVFFlat indexing can support large vector datasets.
- Vector similarity searches scale efficiently with proper indexing.

### 7. **Security**
- Nullable fields (e.g., `email`) avoid storing unnecessary PII.
- Sensitive data access should be controlled at the application level.

---

## Conclusion
This PostgreSQL schema with pgvector extension supports the **AI Invoice Assistant** by providing a robust, scalable, and efficient structure for managing users, invoices, conversations, media, and vector embeddings for semantic search. The validated implementation confirms the proper setup of tables, relationships, and vector data types, enabling powerful natural language queries against invoice data.