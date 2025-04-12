# WhatsApp Invoice Assistant Test UI

This is a Flask-based web application that provides a WhatsApp-like interface for testing the WhatsApp Invoice Assistant. It leverages the existing `tests.interactive_test` module to process messages and files, while adding a visual representation of the agent flow and responses.

## Features

- WhatsApp-inspired chat interface
- Text message input and processing
- File upload and invoice processing
- Agent flow visualization
- Detailed agent response and metadata display
- Database status monitoring
- Mobile-responsive design

## Directory Structure

```
ui/
├── app.py                # Flask application
├── README.md             # This file
├── static/               # Static assets
│   ├── css/              # CSS styles
│   │   └── style.css     # Main stylesheet
│   ├── js/               # JavaScript files
│   │   └── app.js        # Main JavaScript
│   └── images/           # Image assets
└── templates/            # HTML templates
    └── index.html        # Main interface template
```

## Requirements

- Python 3.8+
- Flask
- WhatsApp Invoice Assistant (main project)

## Installation

1. Make sure you have the main WhatsApp Invoice Assistant project set up and working.
2. Install Flask if not already installed:
   ```
   pip install flask
   ```
   
   Or use the Makefile command:
   ```
   make ui-install
   ```

## Usage

1. Run the Flask application:
   ```
   cd ui
   python app.py --port 5001
   ```
   
   Or use the Makefile command:
   ```
   make ui-run
   ```

2. Open your browser and navigate to `http://localhost:5001`

3. Interact with the assistant by:
   - Typing messages in the chat input
   - Uploading invoice files using the paperclip icon
   - Using commands like `/help` to get assistance
   
## Port Configuration

By default, the application runs on port 5001 to avoid conflicts with port 5000. You can specify a different port:

```
python app.py --port 8080
```

## Testing the APIs

You can test the API endpoints using curl:

```bash
# Initialize the test environment
curl http://localhost:5001/api/init

# Send a test message
curl -X POST -H "Content-Type: application/json" -d '{"message": "Show me my invoices"}' http://localhost:5001/api/message

# Get agent flow information
curl http://localhost:5001/api/agent-flow
```

## Commands

The UI supports the same commands as the interactive test:

- `/help` - Show available commands
- `/exit` - Exit the test (when running in terminal)
- `/new` - Start a new conversation
- `/file <path>` - Process a file (primarily used in terminal, use the upload button in UI)

## Agent Flow Panel

The right panel shows detailed information about the agent's processing:

- **Current Intent**: The detected intent of the user's message
- **Workflow Steps**: The sequence of agents involved in processing
- **Agent Responses**: Raw responses from the agent including metadata
- **Database Status**: Current counts of invoices and items in the database

## Development

To extend or modify the UI:

1. The Flask routes are defined in `app.py`
2. The HTML structure is in `templates/index.html`
3. Styles are in `static/css/style.css`
4. JavaScript functionality is in `static/js/app.js`

To add more detailed agent flow visualization:

1. Modify the `updateAgentPanel()` function in `app.js`
2. Add additional metadata tracking in the Flask app
3. Update the UI components in `index.html` as needed

## Integration with Interactive Test

The UI calls the same functions used by the interactive test module, ensuring consistent behavior while adding visual representation of the process. The `handle_message` and `handle_command` functions from `tests.interactive_test` are used directly to process user inputs. 