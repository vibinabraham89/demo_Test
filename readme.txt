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


🔹 Step 1 — Run Azure SQL Edge

In PowerShell:

docker run -d `
  --name azure-sql-edge `
  -e "ACCEPT_EULA=1" `
  -e "MSSQL_SA_PASSWORD=Password@123" `
  -p 1433:1433 `
  mcr.microsoft.com/azure-sql-edge:latest


Password must meet SQL rules → Password@123 works.

Container will run SQL on port 1433.

🔹 Step 2 — Run Service Bus Emulator

Then:

docker run -d `
  --name service-bus-emulator `
  --link azure-sql-edge:sql1 `
  -p 5672:5672 `
  -p 5671:5671 `
  -p 443:443 `
  -p 9354:9354 `
  mcr.microsoft.com/azure-messaging/servicebus-emulator:latest


--link azure-sql-edge:sql1 connects emulator to SQL container.

Ports (5672, 5671, 443, 9354) are the same ones Service Bus uses.

🔹 Step 3 — Verify

Check if both are running:

docker ps


You should see azure-sql-edge and service-bus-emulator containers.

🔹 Step 4 — Connect from your app

Use this connection string in your app:

Endpoint=sb://localhost/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=Eby8vdM02xNOcqFlqUwJ7r1dvbjG3rJHB5Bsn4I4k9E=;UseDevelopmentEmulator=true;


That’s the built-in dev key the emulator exposes.


docker rm -f service-bus-emulator -> remove

# list containers
docker ps --format "table {{.ID}}\t{{.Image}}\t{{.Names}}\t{{.Ports}}"

# check logs for emulator container (replace name or id as seen above)
docker logs <container_name_or_id> --tail 100


What to look for:

You should see a container for the Service Bus emulator and for SQL Edge.

Ports mapping should include 0.0.0.0:5672->5672/tcp (or similar). If no 5672 published, the host can't reach the emulator AMQP port.

If docker ps shows no :5672 port mapping, that’s why the socket error happens.


# Windows PowerShell
Test-NetConnection -ComputerName localhost -Port 5672

# quick raw TCP test (PowerShell Core or cmd):
# (shows connection refused if not listening)
tnc localhost 5672  # alias to Test-NetConnection in some shells
Expected: TcpTestSucceeded : True.
If False, either container not listening or firewall/port mapping problem.


From the docker logs output you ran above, search for errors or lines that say what IP/ports it bound to. Paste the last ~50 lines if you're unsure.






