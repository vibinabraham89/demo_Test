6) Step-by-step PowerShell commands to run everything

Open VS Code and three terminals: Terminal A (FastAPI), Terminal B (Worker #1), Terminal C (Worker #2 optional). Also have Terminal D (for tests).

A — Prepare project & venv (once)
cd C:\path\to\soc-triage\src
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
# copy .env.example to .env and edit if needed:
Copy-Item .env.example .env


Open .env and ensure SERVICEBUS_CONNECTION_STRING is correct for your emulator or real Azure.

B — Start Service Bus emulator (if you want local dev)

You can either:

Use Microsoft Service Bus Emulator (requires Docker & the installer repo). If you have it, run its LaunchEmulator.sh in WSL or follow its README.

Or point SERVICEBUS_CONNECTION_STRING to a real Azure Service Bus namespace connection string.

(If you need exact emulator install steps, tell me and I’ll paste them. For now assume emulator is running and listening.)

C — Run FastAPI (Terminal A)
cd C:\path\to\soc-triage\src
.venv\Scripts\Activate.ps1
# ensure .env is in same folder (we loaded python-dotenv in code)
uvicorn webhook_servicebus:app --host 0.0.0.0 --port 7071 --reload


You should see Uvicorn running on http://0.0.0.0:7071.

D — Run Worker(s) (Terminal B, Terminal C, ...)

Open Terminal B:

cd C:\path\to\soc-triage
.venv\Scripts\Activate.ps1
# set PYTHONPATH so 'src' package imports work:
$env:PYTHONPATH = (Resolve-Path ".\src").Path
python .\src\worker_servicebus_oneper.py


Optionally open Terminal C and repeat to start another worker for parallel processing.

Each worker will log status and pick messages from the Service Bus queue.

E — Test by sending webhook (Terminal D)

Use PowerShell so quoting is easy:

$body = @{ incident_id = "INC-TEST-1" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:7071/webhook" -Method POST -Body $body -ContentType "application/json" -Verbose


Expected:

FastAPI terminal logs Enqueued ...

One of the worker terminals logs fetching payload, calls triage_automation (your module prints/display), then completes the message.

If you want to simulate triage_automation failure, modify the stub to raise an exception and watch the worker log the CRITICAL message with stack trace and abandon the message so it gets retried/ eventually DLQed.

7) Troubleshooting checklist

If worker ImportError for src.api...:

Ensure you ran worker from project root and set PYTHONPATH to .\src (the inner package root).

Confirm the folder soc-triage/src/src/api/soar/client.py exists (two levels: project src, and package src). If your package is named differently, change imports accordingly.

If Service Bus connection fails:

Confirm emulator is running OR your cloud connection string is correct.

If emulator, ensure Endpoint=sb://localhost and UseDevelopmentEmulator=true (emulator docs may require different SAS key).

If messages never get processed:

Check worker logs to ensure it connected and polling.

Use Azure CLI or SDK to peek messages in queue to see if they are enqueued.

If FastAPI returns missing incident_id:

Ensure you POST JSON correctly using PowerShell Invoke-RestMethod or curl.exe with proper escaping.
