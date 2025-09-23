# worker_servicebus_oneper.py
import os
import sys
import json
import logging
import time
from typing import Any, Dict

from dotenv import load_dotenv
from azure.servicebus import ServiceBusClient

# load .env if present
load_dotenv()

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("worker_servicebus_oneper")

# -------------------------
# Config (use env or provided defaults)
# -------------------------
SERVICEBUS_CONN = os.getenv(
    "SERVICEBUS_CONNECTION_STRING",
    "Endpoint=sb://localhost/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=Eby8vdM02xNOcqFlqUwJ7r1dvbjG3rJHB5Bsn4I4k9E=;UseDevelopmentEmulator=true;"
)
QUEUE_NAME = os.getenv("SERVICEBUS_QUEUE", "incidents")
RECEIVE_WAIT = int(os.getenv("WORKER_RECEIVE_WAIT", "10"))

if not SERVICEBUS_CONN:
    raise RuntimeError("SERVICEBUS_CONNECTION_STRING not set in environment")

# Ensure the package root is on sys.path so `from src...` imports work.
# We assume this file lives at project/src/worker_servicebus_oneper.py and your package is at project/src/src/...
this_dir = os.path.abspath(os.path.dirname(__file__))  # typically project/src
if this_dir not in sys.path:
    sys.path.insert(0, this_dir)

# -------------------------
# Attempt to import your modules (your code must be in the package path)
# -------------------------
try:
    from src.api.soar.client import unifiedsoarclient
    from src.service.triage_automation import triage_automation
except Exception as e:
    logger.exception(
        "Failed to import src.api.soar.client or src.service.triage_automation. "
        "Make sure PYTHONPATH includes the folder that contains the 'src' package. Error: %s", e
    )
    raise

# -------------------------
# Helpers
# -------------------------
def fetch_ticket_payload(incident_id: str) -> Dict[str, Any]:
    """
    Use unifiedsoarclient to fetch the unified payload for the incident_id.
    If your SOAR client expects an int, we try to convert here.
    """
    logger.info("Fetching ticket payload for incident_id=%s", incident_id)
    client = unifiedsoarclient()

    # If the SOAR API expects an int id, convert if possible.
    try:
        # If incident_id looks numeric, cast to int; otherwise keep string.
        incident_id_param: Any
        if isinstance(incident_id, str) and incident_id.isdigit():
            incident_id_param = int(incident_id)
        else:
            incident_id_param = incident_id
    except Exception:
        incident_id_param = incident_id

    # Call the SOAR client (may raise exceptions which will be handled by caller)
    ticket_payload = client.create_unified_payload(incident_id_param)
    try:
        size = len(json.dumps(ticket_payload))
    except Exception:
        size = None
    logger.info("Fetched ticket payload for %s (approx size=%s bytes)", incident_id, size)
    return ticket_payload


# -------------------------
# Main loop
# -------------------------
def run_worker_loop():
    sb_client = ServiceBusClient.from_connection_string(SERVICEBUS_CONN)
    logger.info("Worker connecting to Service Bus queue=%s", QUEUE_NAME)

    with sb_client:
        receiver = sb_client.get_queue_receiver(queue_name=QUEUE_NAME, max_wait_time=RECEIVE_WAIT)
        with receiver:
            logger.info("Worker started and listening for messages...")
            while True:
                try:
                    messages = receiver.receive_messages(max_message_count=1, max_wait_time=RECEIVE_WAIT)
                    messages = list(messages)
                    if not messages:
                        time.sleep(1)
                        continue

                    for msg in messages:
                        try:
                            # Robust body extraction: SDK may return list of parts or bytes
                            body_obj = msg.body
                            if isinstance(body_obj, (list, tuple)):
                                parts = []
                                for part in body_obj:
                                    if isinstance(part, memoryview):
                                        parts.append(part.tobytes())
                                    elif isinstance(part, (bytes, bytearray)):
                                        parts.append(bytes(part))
                                    elif isinstance(part, str):
                                        parts.append(part.encode("utf-8"))
                                    else:
                                        parts.append(str(part).encode("utf-8"))
                                joined = b"".join(parts)
                                body_text = joined.decode("utf-8")
                            else:
                                try:
                                    body_text = body_obj.decode("utf-8") if isinstance(body_obj, (bytes, bytearray)) else str(body_obj)
                                except Exception:
                                    body_text = str(body_obj)

                            # Parse JSON message
                            try:
                                payload = json.loads(body_text)
                            except Exception:
                                logger.warning("Invalid JSON message body; dead-lettering. Body preview: %s", body_text[:200])
                                try:
                                    receiver.dead_letter_message(msg, reason="invalid_json", error_description="Message body not valid JSON")
                                except Exception:
                                    logger.exception("Failed to dead-letter invalid JSON message")
                                continue

                            incident_id = payload.get("incident_id")
                            if not incident_id:
                                logger.warning("Message missing incident_id; dead-lettering.")
                                try:
                                    receiver.dead_letter_message(msg, reason="missing_incident_id", error_description="No incident_id in message")
                                except Exception:
                                    logger.exception("Failed to dead-letter message missing incident_id")
                                continue

                            # Optional: idempotency check (TODO)

                            # Fetch full ticket payload from SOAR
                            try:
                                ticket_payload = fetch_ticket_payload(str(incident_id))
                            except Exception as e:
                                logger.exception("Failed to fetch ticket payload for %s: %s", incident_id, e)
                                try:
                                    # transient failure -> abandon for retry
                                    receiver.abandon_message(msg)
                                except Exception:
                                    logger.exception("Failed to abandon message after payload fetch failure")
                                continue

                            # Call triage_automation (no extra logging of result; triage_automation handles display)
                            try:
                                triage_automation(ticket_payload)
                            except Exception as e:
                                # Critical logging with full traceback as requested
                                logger.critical(
                                    "Critical issue during triage process for incident %s: %s",
                                    incident_id, e,
                                    exc_info=True
                                )
                                try:
                                    receiver.abandon_message(msg)
                                except Exception:
                                    logger.exception("Failed to abandon message after triage_automation failure")
                                continue

                            # On success -> complete message
                            try:
                                receiver.complete_message(msg)
                                logger.info("Completed Service Bus message for incident=%s", incident_id)
                            except Exception as e:
                                logger.exception("Failed to complete message for %s: %s", incident_id, e)
                                try:
                                    receiver.abandon_message(msg)
                                except Exception:
                                    logger.exception("Failed to abandon message after complete failure")

                        except Exception as msg_exc:
                            logger.exception("Unexpected error processing message; abandoning. Error: %s", msg_exc)
                            try:
                                receiver.abandon_message(msg)
                            except Exception:
                                logger.exception("Failed to abandon message after unexpected error")

                except KeyboardInterrupt:
                    logger.info("Worker stopping by KeyboardInterrupt")
                    return
                except Exception as outer_exc:
                    logger.exception("Top-level worker loop error, sleeping briefly then retrying: %s", outer_exc)
                    time.sleep(2)


if __name__ == "__main__":
    run_worker_loop()
