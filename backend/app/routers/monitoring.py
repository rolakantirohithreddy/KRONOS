"""Monitoring endpoints – wire traffic visibility via arp_redirect_service."""

import logging
import threading
import traceback
from collections import deque
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import arp_redirect_service
from app.services.incident_service import save_incident
from app.models.user import SessionLocal

logger = logging.getLogger("kronos.monitoring")

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# ---------- module-level state ----------
_current_target_ip: str | None = None
_state_lock = threading.Lock()

_log_buffer: deque = deque(maxlen=200)

_last_cycle_at: datetime | None = None
_packets_last_window: int = 0
_capture_stop_event: threading.Event | None = None
_capture_thread: threading.Thread | None = None


def _log(level: str, message: str) -> None:
    """Simultaneously logs to Python logging AND appends to _log_buffer."""
    if level.upper() == "ERROR":
        logger.error(message)
    elif level.upper() == "WARNING":
        logger.warning(message)
    else:
        logger.info(message)
        
    _log_buffer.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "message": message
    })


# ---------- request / response models ----------
class MonitorStartRequest(BaseModel):
    target_ip: str
    gateway_ip: str | None = None


class MonitorStopRequest(BaseModel):
    target_ip: str | None = None  # optional – defaults to current target


# ---------- capture loop ----------
def _capture_loop(target_ip: str):
    global _last_cycle_at, _packets_last_window

    from app.services.flow_extractor import run_capture_cycle  # lazy import
    
    _log("INFO", f"Capture loop started for target {target_ip}")
    
    while _capture_stop_event and not _capture_stop_event.is_set():
        try:
            result = run_capture_cycle(target_ip, window_seconds=5.0)
            
            packets = result.get('packets_captured', 0)
            flows = result.get('flows_extracted', 0)
            _log("INFO", f"Cycle complete: {packets} packets, {flows} flows")
            
            for flow in result.get('results', []):
                source_ip = flow.get('source_ip', target_ip)
                features = flow.get('features', {})
                prediction_info = flow.get('prediction', {})
                pred_label = prediction_info.get('prediction', 'Benign')
                confidence = prediction_info.get('confidence', 0.0)
                risk_label = flow.get('risk_label', 'Low')
                
                # Log ALL features for every flow (telemetry -- always visible in Live Logs)
                _log("INFO",
                     f"  Flow src={source_ip} | prediction={pred_label} "
                     f"confidence={confidence:.4f} risk={risk_label}")
                _log("INFO", f"    features={features}")
                
                if pred_label != 'Benign':
                    risk_score = confidence * 100
                    
                    pipeline_result = {
                        "detection": {
                            "prediction": pred_label,
                            "confidence": confidence,
                            "timestamp": datetime.now(timezone.utc)
                        },
                        "risk_assessment": {
                            "risk_label": risk_label,
                            "risk_score": risk_score
                        },
                        "evidence": {
                            "evidence_statements": [
                                f"Live capture detected {pred_label} from {source_ip} with {confidence:.2f} confidence.",
                                f"Top features: {prediction_info.get('top_features', [])}"
                            ]
                        },
                        "agent_latencies_ms": {
                            "total": prediction_info.get('latency_ms', 0.0)
                        },
                        "request_id": str(uuid4())
                    }
                    
                    db = SessionLocal()
                    try:
                        record = save_incident(db, pipeline_result, source='live', source_ip=source_ip)
                        if record is not None:
                            occ = getattr(record, 'occurrence_count', 1) or 1
                            if occ > 1:
                                _log("INFO", f"  >>> INCIDENT UPDATED: {pred_label} from {source_ip} (risk={risk_label}, occurrences={occ})")
                            else:
                                _log("INFO", f"  >>> INCIDENT SAVED: {pred_label} from {source_ip} (risk={risk_label})")
                        else:
                            _log("INFO", f"  --- Filtered (below threshold or benign): {pred_label} from {source_ip} risk={risk_label}")
                    except Exception as e:
                        _log("ERROR", f"Failed to save incident: {e}")
                    finally:
                        db.close()
            
            with _state_lock:
                _last_cycle_at = datetime.now(timezone.utc)
                _packets_last_window = packets
                
        except Exception as exc:
            err_msg = f"Error in capture cycle: {exc}\n{traceback.format_exc()}"
            _log("ERROR", err_msg)
            
        if _capture_stop_event:
            _capture_stop_event.wait(1.0)
            
    _log("INFO", f"Capture loop stopped for target {target_ip}")


# ---------- endpoints ----------

@router.post("/start")
async def start_monitoring(payload: MonitorStartRequest) -> dict[str, Any]:
    global _current_target_ip, _capture_stop_event, _capture_thread

    with _state_lock:
        if _current_target_ip and _current_target_ip != payload.target_ip:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Already monitoring {_current_target_ip}. "
                    f"Stop it first before starting a new target."
                ),
            )

    try:
        redirect_result = arp_redirect_service.start_redirect(
            target_ip=payload.target_ip,
            gateway_ip=payload.gateway_ip,
        )
    except RuntimeError as exc:
        _log("ERROR", f"start_redirect failed for {payload.target_ip}: {exc}")
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        _log("ERROR", f"Unexpected error in start_redirect for {payload.target_ip}: {exc}")
        raise HTTPException(
            status_code=422,
            detail=f"Failed to start traffic visibility: {exc}",
        )

    with _state_lock:
        _current_target_ip = payload.target_ip
        
        # Stop existing loop if somehow running
        if _capture_stop_event:
            _capture_stop_event.set()
        if _capture_thread:
            _capture_thread.join(timeout=2)
            
        _capture_stop_event = threading.Event()
        _capture_thread = threading.Thread(
            target=_capture_loop, args=(payload.target_ip,), daemon=True
        )
        _capture_thread.start()

    _log("INFO", f"Monitoring started for {payload.target_ip}")
    return {
        "status": "monitoring_started",
        "target_ip": payload.target_ip,
        "redirect": redirect_result,
    }


@router.post("/stop")
async def stop_monitoring(payload: MonitorStopRequest | None = None) -> dict[str, Any]:
    global _current_target_ip, _capture_stop_event, _capture_thread

    with _state_lock:
        target = (payload.target_ip if payload and payload.target_ip else None) or _current_target_ip

    if not target:
        raise HTTPException(
            status_code=404,
            detail="No device is currently being monitored.",
        )

    # Stop the capture loop before ARP redirect
    if _capture_stop_event:
        _capture_stop_event.set()
    if _capture_thread:
        _capture_thread.join(timeout=10)
        
    with _state_lock:
        _capture_thread = None
        _capture_stop_event = None

    redirect_result = arp_redirect_service.stop_redirect(target)

    with _state_lock:
        if _current_target_ip == target:
            _current_target_ip = None
            
        # Reset capture metrics
        global _last_cycle_at, _packets_last_window
        _last_cycle_at = None
        _packets_last_window = 0

    _log("INFO", f"Monitoring stopped for {target}")
    return {
        "status": "monitoring_stopped",
        "target_ip": target,
        "redirect": redirect_result,
    }


@router.get("/status")
async def monitoring_status() -> dict[str, Any]:
    """Return current monitoring and ARP redirect status."""
    with _state_lock:
        target = _current_target_ip
        last_cycle = _last_cycle_at
        packets_last_window = _packets_last_window

    arp_status = arp_redirect_service.get_status()
    
    # Determine if ARP redirect is active based on typical dict structures
    # like {"targets": [...]}, {"active_targets": [...]}, or just bool
    arp_redirect_active = False
    if isinstance(arp_status, dict):
        if "targets" in arp_status:
            arp_redirect_active = bool(arp_status["targets"])
        elif "active_targets" in arp_status:
            arp_redirect_active = bool(arp_status["active_targets"])
        else:
            arp_redirect_active = target is not None
    elif isinstance(arp_status, list):
        arp_redirect_active = len(arp_status) > 0
    else:
        arp_redirect_active = bool(arp_status)

    now = datetime.now(timezone.utc)
    capture_loop_alive = False
    if last_cycle and (now - last_cycle).total_seconds() <= 15:
        capture_loop_alive = True

    return {
        "monitoring_active": target is not None,
        "current_target_ip": target,
        "arp_redirect": arp_status,
        "arp_redirect_active": arp_redirect_active,
        "capture_loop_alive": capture_loop_alive,
        "last_cycle_at": last_cycle.isoformat() if last_cycle else None,
        "packets_seen_last_window": packets_last_window,
    }


@router.get("/logs")
async def monitoring_logs() -> list[dict[str, str]]:
    """Return the recent in-memory logs."""
    return list(_log_buffer)
