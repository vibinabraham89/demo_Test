3 — Run instructions (PowerShell, copy/paste)

1.Ensure you have a Python venv & installed requirements. From soc-triage/src:

cd C:\path\to\soc-triage\src
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install fastapi uvicorn python-dotenv azure-servicebus requests
# (or pip install -r requirements.txt if you have the file)


2.Put the .env (from step 0) in soc-triage/src/.env.

SERVICEBUS_CONNECTION_STRING=Endpoint=sb://localhost/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=Eby8vdM02xNOcqFlqUwJ7r1dvbjG3rJHB5Bsn4I4k9E=;UseDevelopmentEmulator=true;
SERVICEBUS_QUEUE=incidents
RESULT_CALLBACK_URL=http://localhost:7071/process_result

3.Start FastAPI (Terminal A):

cd C:\path\to\soc-triage\src
.venv\Scripts\Activate.ps1
uvicorn webhook_servicebus:app --host 0.0.0.0 --port 7071 --reload


4.Start Worker (Terminal B). IMPORTANT: run from project root and set PYTHONPATH so from src... resolves:

cd C:\path\to\soc-triage
.venv\Scripts\Activate.ps1
# set PYTHONPATH to the inner src package folder:
$env:PYTHONPATH = (Resolve-Path ".\src").Path
# run worker
python .\src\worker_servicebus_oneper.py


Start more workers (Terminal C, D...) repeating Step 4 to get parallel processing — Service Bus will distribute messages.

5.Send a test webhook (Terminal D):

$body = @{ incident_id = "12345" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:7071/webhook" -Method POST -Body $body -ContentType "application/json" -Verbose


Watch FastAPI logs and the worker terminal(s). Worker should fetch payload via your unifiedsoarclient, call triage_automation, and then complete the message.

