
# AI Invoice Assistant: Complete Application Flow and Query Types

## Overview
The **AI Invoice Assistant** is a WhatsApp-based AI application designed to assist users in managing their invoices and business expenses. It processes both text-based queries and file uploads (e.g., images, PDFs, Excel, CSV) and responds based on the detected intent or input type. Built using a **LangGraph-based architecture** with memory integration, the application ensures conversational context is maintained across interactions. The technical stack includes:

- **Database**: PostgresSQL (stores user data, invoices, and conversation history)
- **LLM**: GPT-4o-mini (handles intent classification, data extraction, and SQL query generation)
- **Framework**: FastAPI (powers the server-side logic)
- **WhatsApp Integration**: Twilio (enables communication via WhatsApp)
- **Workflow Orchestration**: LangGraph (manages the flow of queries through various nodes)

Every node in the LangGraph workflow follows a consistent structure, with differences only in prompts and configurations (e.g., LLM model, specific variables) defined in a `constants.py` file. All responses are formatted consistently using a dedicated `Response Formatter Node` before being sent to the user.

---

## Query Types, Inputs, Flows, and Expected Responses

The application categorizes user inputs into seven distinct query types. Below, each type is detailed with examples of input queries, the processing flow, and the expected response.

### 1. GREETING
#### Input Queries
- Examples: "Hey," "Hi," "Hello," "Good morning," "Hey there."
- Description: Simple salutations or introductory messages with no specific request or question.

#### Processing Flow
1. **Input Received**: The user sends a greeting via WhatsApp.
2. **Twilio Webhook**: The message is received by the Twilio webhook and forwarded to the FastAPI server.
3. **Router Node**: Identifies the input as text and routes it to the `Text Intent Classifier Node`.
4. **Text Intent Classifier Node**: Uses GPT-4o-mini to classify the intent as **GREETING**.
5. **Response Preparation**: A predefined greeting template is selected as the response.
6. **Response Formatter Node**: Structures the response with a disclaimer for consistency.
7. **Output Sent**: The formatted response is sent back to the user via Twilio.

#### Expected Response
```
👋 Welcome to InvoiceAgent!

I'm your AI-powered financial assistant for business expenses.

📊 WHAT I CAN DO FOR YOU:
• Extract data from receipts and invoices automatically
• Track and categorize your business expenses
• Analyze your spending patterns and trends
• Find specific invoices when you need them

💬 ASK ME THINGS LIKE:
• "What did I spend at Amazon last month?"
• "Show my restaurant expenses from March"
• "How much have I spent on office supplies?"
• "Find all invoices over $100"

To get started, simply send a photo of any receipt or invoice, then ask me specific questions about your expenses.

---

*Disclaimer: This is an AI-generated response. Please verify any critical information.*
```

---

### 2. GENERAL
#### Input Queries
- Examples: "How are you?" "How is the weather?" "Who won the last match?" "What’s your name?" "Tell me a joke."
- Description: Questions or statements unrelated to invoices or expense management.

#### Processing Flow
1. **Input Received**: The user sends a general query via WhatsApp.
2. **Twilio Webhook**: The message is received by the Twilio webhook and passed to the FastAPI server.
3. **Router Node**: Identifies the input as text and routes it to the `Text Intent Classifier Node`.
4. **Text Intent Classifier Node**: Uses GPT-4o-mini to classify the intent as **GENERAL**.
5. **Response Preparation**: A predefined general response template is selected, informing the user that only invoice-related queries are supported.
6. **Response Formatter Node**: Structures the response with a disclaimer and contact information.
7. **Output Sent**: The formatted response is sent back to the user via Twilio.

#### Expected Response
```
❗ I can only answer invoice-related queries.

⬇️ Here's what I can help you with instead:

👋 Welcome to InvoiceAgent!

I'm your AI-powered financial assistant for business expenses.

📊 WHAT I CAN DO FOR YOU:
• Extract data from receipts and invoices automatically
• Track and categorize your business expenses
• Analyze your spending patterns and trends
• Find specific invoices when you need them

💬 ASK ME THINGS LIKE:
• "What did I spend at Amazon last month?"
• "Show my restaurant expenses from March"
• "How much have I spent on office supplies?"
• "Find all invoices over $100"

To get started, simply send a photo of any receipt or invoice, then ask me specific questions about your expenses.

Questions? Email raj.abhay6@gmail.com

---

*Disclaimer: This is an AI-generated response. Please verify any critical information.*
```

---

### 3. INVOICE QUERY
#### Input Queries
- Examples: "What did I spend at Amazon last month?" "Show my restaurant expenses from March," "How much have I spent on office supplies?" "Find all invoices over $100."
- Description: Questions about existing invoices or expense data stored in the system.

#### Processing Flow
1. **Input Received**: The user sends an invoice-related query via WhatsApp.
2. **Twilio Webhook**: The message is received by the Twilio webhook and passed to the FastAPI server.
3. **Router Node**: Identifies the input as text and routes it to the `Text Intent Classifier Node`.
4. **Text Intent Classifier Node**: Uses GPT-4o-mini to classify the intent as **INVOICE QUERY**.
5. **SQL Converter Node**: Converts the natural language query into an SQL query using the SQLDatabase toolkit and GPT-4o-mini.
6. **Database Query**: Executes the generated SQL query against the PostgresSQL database to retrieve relevant data.
7. **Response Formatter Node**: Structures the query results into a readable format with a disclaimer.
8. **Output Sent**: The formatted response is sent back to the user via Twilio.

#### Expected Response
```
📊 Here are your expenses at Amazon last month:

- Total Spent: $250.00
- Number of Invoices: 3
- Average Invoice Amount: $83.33

💡 Tip: You can ask for more details or filter by date, vendor, or amount.

---

*Disclaimer: This is an AI-generated response. Please verify the data for accuracy.*
```

---

### 4. INVOICE GENERATION
#### Input Queries
- Examples: "Create an invoice for $100 from Amazon on March 5," "Generate an invoice for $50 from Walmart today," "Make an invoice for $200 from Office Depot on April 10."
- Description: Requests to create a new invoice based on text input specifying details like amount, vendor, and date.

#### Processing Flow
1. **Input Received**: The user sends a request to create an invoice via WhatsApp.
2. **Twilio Webhook**: The message is received by the Twilio webhook and passed to the FastAPI server.
3. **Router Node**: Identifies the input as text and routes it to the `Text Intent Classifier Node`.
4. **Text Intent Classifier Node**: Uses GPT-4o-mini to classify the intent as **INVOICE GENERATION**.
5. **Invoice Generator Node**: Extracts entities (e.g., amount, vendor, date) from the text using GPT-4o-mini.
6. **Invoice Creation**: Populates a default invoice template with the extracted entities and generates a PDF.
7. **Storage**: Stores the generated invoice in the PostgresSQL database.
8. **Response Formatter Node**: Prepares a confirmation message with a link to the invoice and a disclaimer.
9. **Output Sent**: The formatted response, along with the invoice PDF, is sent back to the user via Twilio.

#### Expected Response
```
📄 Your invoice has been created successfully!

- Vendor: Amazon
- Date: March 5, 2023
- Amount: $100.00

You can view the invoice [here](link-to-invoice-pdf).

💡 Tip: You can ask to create more invoices or query existing ones.

---

*Disclaimer: This is an AI-generated invoice. Please verify the details.*
```

---

### 5. INVALID INVOICE
#### Input Queries
- Examples: Upload an image of a selfie, a meme, a blank page, or any non-invoice document.
- Description: File uploads that are not valid invoices or receipts.

#### Processing Flow
1. **Input Received**: The user uploads a file via WhatsApp.
2. **Twilio Webhook**: The file is received by the Twilio webhook and passed to the FastAPI server.
3. **Router Node**: Identifies the input as a file and routes it to the `File Validator Node`.
4. **File Validator Node**: Uses image validation techniques (e.g., OCR with GPT-4o-mini) to determine if the file is a valid invoice; classifies it as **INVALID INVOICE** if not.
5. **Response Preparation**: Prepares a rejection message indicating the file is not a valid invoice.
6. **Response Formatter Node**: Structures the response with a disclaimer and a tip.
7. **Output Sent**: The formatted response is sent back to the user via Twilio.

#### Expected Response
```
❌ The uploaded file is not a valid invoice.

Please upload a clear image of a receipt or invoice.

💡 Tip: Ensure the image is well-lit and the text is readable.

---

*Disclaimer: This is an AI-generated response. Please try again with a valid invoice.*
```

---

### 6. VALID INVOICE
#### Input Queries
- Examples: Upload a clear image of an invoice, a PDF receipt, an Excel expense sheet, or a CSV file with invoice data.
- Description: File uploads that are valid invoices or receipts containing extractable data.

#### Processing Flow
1. **Input Received**: The user uploads a file via WhatsApp.
2. **Twilio Webhook**: The file is received by the Twilio webhook and passed to the FastAPI server.
3. **Router Node**: Identifies the input as a file and routes it to the `File Validator Node`.
4. **File Validator Node**: Confirms the file is a valid invoice using validation techniques.
5. **Data Extractor Node**: Uses GPT-4o-mini to extract relevant data (e.g., vendor, date, amount) from the file.
6. **Database Storage**: Maps the extracted data to the PostgresSQL schema and stores it.
7. **Response Preparation**: Prepares a confirmation message with the extracted data.
8. **Response Formatter Node**: Structures the response with a disclaimer and a tip.
9. **Output Sent**: The formatted response is sent back to the user via Twilio.

#### Expected Response
```
✅ Invoice uploaded and processed successfully!

- Vendor: Amazon
- Date: March 5, 2023
- Amount: $100.00

The data has been stored in your account.

💡 Tip: You can now query this invoice using natural language.

---

*Disclaimer: This is an AI-generated response. Please verify the extracted data.*
```

---

### 7. UNSUPPORTED FORMATS
#### Input Queries
- Examples: Upload a video file, an audio recording, a ZIP file, or any format not supported (e.g., not text, image, PDF, Excel, or CSV).
- Description: Inputs that are neither text nor supported file types.

#### Processing Flow
1. **Input Received**: The user uploads an unsupported file via WhatsApp.
2. **Twilio Webhook**: The file is received by the Twilio webhook and passed to the FastAPI server.
3. **Router Node**: Identifies the input as an unsupported format (not text or a supported file type).
4. **Response Preparation**: Prepares a default message indicating the format is unsupported.
5. **Response Formatter Node**: Structures the response with a disclaimer and instructions.
6. **Output Sent**: The formatted response is sent back to the user via Twilio.

#### Expected Response
```
⚠️ Unsupported format.

We only support text, images, PDFs, Excel, and CSV files.

Please upload a valid file or send a text query.

---

*Disclaimer: This is an AI-generated response. Please try again with a supported format.*
```

---

## Summary of Query Types and Flows

| **Query Type**      | **Input Type** | **Example Inputs**                              | **Flow Overview**                                                                 | **Expected Response**            |
|---------------------|----------------|------------------------------------------------|-----------------------------------------------------------------------------------|----------------------------------|
| GREETING            | Text           | "Hey," "Hi," "Hello"                           | Classify intent → Prepare greeting → Format → Send                                | Default greeting template        |
| GENERAL             | Text           | "How are you?" "How’s the weather?"            | Classify intent → Prepare general response → Format → Send                        | Default general template         |
| INVOICE QUERY       | Text           | "What did I spend at Amazon last month?"       | Classify intent → Convert to SQL → Execute query → Format → Send                  | Dynamic query results            |
| INVOICE GENERATION  | Text           | "Create an invoice for $100 from Amazon"       | Classify intent → Extract entities → Generate invoice → Format → Send             | Invoice creation confirmation    |
| INVALID INVOICE     | File           | Image of a selfie or meme                      | Validate file → Reject if invalid → Format → Send                                 | Rejection message                |
| VALID INVOICE       | File           | Image of a clear invoice                       | Validate file → Extract data → Store in DB → Format → Send                        | Data extraction confirmation     |
| UNSUPPORTED FORMATS | Other          | Video, audio, or ZIP file                      | Identify unsupported format → Prepare response → Format → Send                    | Unsupported format message       |

---

## Technical Notes
- **Memory Integration**: LangGraph’s memory ensures conversational context is preserved, allowing the assistant to reference previous interactions.
- **Node Consistency**: All nodes share the same structural design; differences lie in prompts and configurations (e.g., LLM model, variables) stored in `constants.py`.
- **Response Formatting**: The `Response Formatter Node` ensures every response is consistently structured and includes a disclaimer for transparency.
- **Scalability**: The use of FastAPI and PostgresSQL supports efficient handling of user requests and data storage.
- **WhatsApp Integration**: Twilio enables seamless communication, supporting both text and file-based interactions.

This document provides a comprehensive guide to the **AI Invoice Assistant**, detailing how it processes each query type and what users can expect in response, ensuring a clear and consistent experience.