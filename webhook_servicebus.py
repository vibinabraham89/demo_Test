# webhook_servicebus.py
import os
import json
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from dotenv import load_dotenv

# load .env if present
load_dotenv()

# --- Config with sensible defaults from your provided values ---
SERVICEBUS_CONN = os.getenv(
    "SERVICEBUS_CONNECTION_STRING",
    "Endpoint=sb://localhost/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=Eby8vdM02xNOcqFlqUwJ7r1dvbjG3rJHB5Bsn4I4k9E=;UseDevelopmentEmulator=true;"
)
QUEUE_NAME = os.getenv("SERVICEBUS_QUEUE", "incidents")
RESULT_CALLBACK_URL = os.getenv("RESULT_CALLBACK_URL", "http://localhost:7071/process_result")

# Basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("webhook_servicebus")

if not SERVICEBUS_CONN:
    raise RuntimeError("SERVICEBUS_CONNECTION_STRING must be set")

app = FastAPI(title="Webhook -> ServiceBus producer")


def send_to_servicebus(payload: dict) -> None:
    """
    Send a JSON payload to the Service Bus queue.
    """
    sb = ServiceBusClient.from_connection_string(SERVICEBUS_CONN)
    with sb:
        sender = sb.get_queue_sender(queue_name=QUEUE_NAME)
        with sender:
            msg_body = json.dumps(payload)
            msg = ServiceBusMessage(msg_body)
            # If incident_id present, set message_id for potential duplicate detection
            if payload.get("incident_id"):
                msg.message_id = payload["incident_id"]
            sender.send_messages(msg)
    logger.info("Enqueued to ServiceBus queue=%s: incident_id=%s", QUEUE_NAME, payload.get("incident_id"))


@app.post("/webhook")
async def webhook(request: Request):
    """
    Accepts JSON payload from Resilient and enqueues an incident_id to Service Bus.
    Expected minimal input: {"incident_id": "12345"} or {"incident": {"id": "12345"}, ...}
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    incident_id = payload.get("incident_id") or (payload.get("incident") or {}).get("id")
    if not incident_id:
        raise HTTPException(status_code=400, detail="missing incident_id")

    message = {
        "incident_id": str(incident_id),
        "received_at": datetime.now(timezone.utc).isoformat()
    }

    try:
        send_to_servicebus(message)
    except Exception:
        logger.exception("Failed to enqueue message to Service Bus")
        raise HTTPException(status_code=500, detail="enqueue_failed")

    return {"status": "enqueued", "incident_id": incident_id}


@app.post("/process_result")
async def process_result(request: Request):
    """
    Optional endpoint for workers to post back their processing result.
    In production you typically persist these results to DB or blob storage instead.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")
    logger.info("Received processing result: %s", payload)
    return {"status": "ok"}
