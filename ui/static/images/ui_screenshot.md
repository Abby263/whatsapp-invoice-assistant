# WhatsApp Invoice Assistant Testing UI

```
+--------------------------------------+-------------------------------+
|  INVOICE ASSISTANT | Testing Interface                               |
+--------------------------------------+-------------------------------+
|                                     |                               |
|  +--------------------------------+ |  +-------------------------+  |
|  | Welcome to the WhatsApp        | |  | AGENT FLOW             |  |
|  | Invoice Assistant Testing UI.  | |  +-------------------------+  |
|  | Type a message or upload an    | |                               |
|  | invoice file to get started.   | |  Current Intent:              |
|  | Type /help for available       | |  +-------------------------+  |
|  | commands.                      | |  | None                    |  |
|  |                                | |  +-------------------------+  |
|  |                           Now  | |                               |
|  +--------------------------------+ |  Workflow Steps:              |
|                                     |  +-------------------------+  |
|  +--------------------------------+ |  | Waiting for input...    |  |
|  | Show me all my invoices        | |  +-------------------------+  |
|  |                          14:32 | |                               |
|  +--------------------------------+ |  Agent Responses:             |
|                                     |  +-------------------------+  |
|  +--------------------------------+ |  | System                  |  |
|  | I found 3 invoices in your     | |  +-------------------------+  |
|  | account. Here's a summary:     | |  | Ready to process        |  |
|  | - Invoice #1001: $245.50       | |  | requests.               |  |
|  | - Invoice #1002: $89.99        | |  +-------------------------+  |
|  | - Invoice #1003: $150.00       | |                               |
|  |                                | |  Database Status:             |
|  |                          14:32 | |  +-------------------------+  |
|  +--------------------------------+ |  | Invoices: 3 | Items: 8  |  |
|                                     |  +-------------------------+  |
|                                     |                               |
|  +--------------------------------+ |                               |
|  | 📎 [Type a message]      →      | |                               |
|  +--------------------------------+ |                               |
+-------------------------------------+-------------------------------+
```

The UI is designed to look and feel like a WhatsApp conversation interface with additional panels that show agent processing information.

## Key Features Shown

1. **Chat Interface**: Messages are displayed in a WhatsApp-style bubble format with timestamps
2. **File Upload**: A paperclip icon to attach and upload invoice files
3. **Agent Flow Panel**: Shows workflow steps and agent processing information
4. **Database Status**: Displays counts of invoices and items stored in the database

The interface allows testers to interact with the assistant naturally while getting visibility into the internal agent flow process. This facilitates debugging and helps understand the system's decision-making process. 