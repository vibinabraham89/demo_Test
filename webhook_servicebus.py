# webhook_servicebus.py
import os
import json
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook_servicebus")

SERVICEBUS_CONN = os.getenv("SERVICEBUS_CONNECTION_STRING")
QUEUE_NAME = os.getenv("SERVICEBUS_QUEUE", "incidents")
RESULT_CALLBACK_URL = os.getenv("RESULT_CALLBACK_URL", "http://localhost:7071/process_result")

if not SERVICEBUS_CONN:
    raise RuntimeError("SERVICEBUS_CONNECTION_STRING not set in env")

app = FastAPI()


def send_to_servicebus(payload: dict):
    sb = ServiceBusClient.from_connection_string(SERVICEBUS_CONN)
    with sb:
        sender = sb.get_queue_sender(queue_name=QUEUE_NAME)
        with sender:
            msg_body = json.dumps(payload)
            msg = ServiceBusMessage(msg_body)
            if payload.get("incident_id"):
                msg.message_id = payload["incident_id"]
            sender.send_messages(msg)
    logger.info("Enqueued to ServiceBus queue=%s: incident_id=%s", QUEUE_NAME, payload.get("incident_id"))


@app.post("/webhook")
async def webhook(request: Request):
    """
    Receives payload from Resilient. Expects JSON with 'incident_id' (or incident.id).
    Enqueues minimal message to Service Bus.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    incident_id = payload.get("incident_id") or (payload.get("incident") or {}).get("id")
    if not incident_id:
        raise HTTPException(status_code=400, detail="missing incident_id")

    msg = {
        "incident_id": incident_id,
        "received_at": datetime.now(timezone.utc).isoformat()
    }

    try:
        send_to_servicebus(msg)
    except Exception as e:
        logger.exception("failed to send message to ServiceBus")
        raise HTTPException(status_code=500, detail="enqueue_failed")

    return {"status": "enqueued", "incident_id": incident_id}


@app.post("/process_result")
async def process_result(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")
    logger.info("Received processing result: %s", payload)
    # persist result in production; demo just returns OK
    return {"status": "ok"}
