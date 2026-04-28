import logging

import valkey as valkey_client
from flask import Blueprint, abort, current_app, jsonify, make_response, request

import config

stream_bp = Blueprint("stream", __name__)
_log    = logging.getLogger("stream")
_valkey = valkey_client.Valkey(host=config.VALKEY_HOST, port=config.VALKEY_PORT)


def _sender(cage_id: int):
    senders = current_app.config.get("COMMAND_SENDERS", {})
    sender  = senders.get(cage_id)
    if sender is None:
        abort(404)
    return sender


@stream_bp.post("/cage/<int:cage_id>/stream/start")
def stream_start(cage_id: int):
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)
    ok, msg = _sender(cage_id).send("START_STREAMING")
    if ok:
        _valkey.set(f"cage:{cage_id}:streaming", "1")
        _log.info(f"Cage {cage_id}: stream STARTED")
    return jsonify({"ok": ok, "msg": msg})


@stream_bp.post("/cage/<int:cage_id>/stream/stop")
def stream_stop(cage_id: int):
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)
    ok, msg = _sender(cage_id).send("STOP_STREAMING")
    if ok:
        _valkey.set(f"cage:{cage_id}:streaming", "0")
        _valkey.set(f"cage:{cage_id}:recording", "0")
        _log.info(f"Cage {cage_id}: stream STOPPED")
    return jsonify({"ok": ok, "msg": msg})


@stream_bp.post("/cage/<int:cage_id>/recording")
def recording_set(cage_id: int):
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)
    body  = request.get_json(force=True) or {}
    state = bool(body.get("state", False))
    _valkey.set(f"cage:{cage_id}:recording", "1" if state else "0")
    _log.info(f"Cage {cage_id}: recording {'STARTED' if state else 'STOPPED'}")
    return jsonify({"ok": True})


@stream_bp.get("/cage/<int:cage_id>/frame")
def latest_frame(cage_id: int):
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)

    jpeg = _valkey.get(f"cage:{cage_id}:latest_frame")
    if jpeg is None:
        abort(503)

    response = make_response(jpeg)
    response.headers["Content-Type"] = "image/jpeg"
    return response


def video_ws_handler(ws, cage_id: int):
    """Called from ui_main.py @sock.route — streams H264 NAL units to the browser."""
    pubsub = _valkey.pubsub()
    pubsub.subscribe(f"cage:{cage_id}:h264_stream")
    try:
        for message in pubsub.listen():
            if message["type"] == "message":
                ws.send(message["data"])
    except Exception:
        pass
    finally:
        pubsub.unsubscribe()
        pubsub.close()


@stream_bp.get("/cameras/status")
def camera_status():
    status = _valkey.hgetall("camera_status")
    return {k.decode(): v.decode() for k, v in status.items()}


@stream_bp.get("/cameras/peripherals")
def cameras_peripherals():
    """Return fan duty (0–100) and strip state for all cages."""
    result = {}
    for cage_id in range(1, config.N_CAGES + 1):
        fan_raw  = _valkey.get(f"cage:{cage_id}:fan")
        fan_duty = int(fan_raw) if fan_raw and fan_raw != b"" else 0
        result[cage_id] = {
            "fan_duty": fan_duty,
            "strip":    _valkey.get(f"cage:{cage_id}:strip") == b"1",
        }
    return result
