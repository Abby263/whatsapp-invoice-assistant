# Local Operator UI

`ui/app.py` is the local Flask interface for testing the WhatsApp Invoice Assistant without sending every request through Twilio. It mirrors the hosted workspace and calls the same application workflows used by the production Flask app where practical.

## What It Provides

- Receipt upload and chat simulation.
- Clerk-aware user and WhatsApp linking controls when auth env vars are configured.
- Generated invoice creation and analytics views.
- Workflow inspector, storage status, database status, and vector status.
- Light and dark mode through the shared UI assets in `ui/static/`.

## Run Locally

From the repository root:

```bash
make ui-run
```

Open:

```text
http://localhost:5001
```

The command starts the UI against the same workflow API used by the hosted app.

## Useful API Checks

```bash
curl http://localhost:5001/api/init

curl -X POST http://localhost:5001/api/message \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me my latest receipts"}'

curl http://localhost:5001/api/db-status
```

## Source Map

```text
ui/
├── app.py                  # Local Flask app
├── static/css/style.css    # Workspace styles and themes
├── static/js/app.js        # Browser behavior and API calls
├── static/site.webmanifest # PWA metadata
└── templates/index.html    # Main workspace markup
```
