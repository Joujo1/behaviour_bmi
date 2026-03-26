import json
import logging

import valkey as valkey_client
from flask import Blueprint, abort, jsonify, request, current_app

import config

control_bp = Blueprint("control", __name__)
_log = logging.getLogger("stream_control")
_valkey = valkey_client.Valkey(host=config.VALKEY_HOST, port=config.VALKEY_PORT)


def _sender(cage_id: int):
    senders = current_app.config.get("COMMAND_SENDERS", {})
    sender = senders.get(cage_id)
    if sender is None:
        abort(404)
    return sender


@control_bp.post("/cage/<int:cage_id>/stream/start")
def stream_start(cage_id: int):
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)
    ok, msg = _sender(cage_id).send("START_STREAMING")
    if ok:
        _valkey.set(f"cage:{cage_id}:streaming", "1")
        _log.info(f"Cage {cage_id}: stream STARTED")
    return jsonify({"ok": ok, "msg": msg})


@control_bp.post("/cage/<int:cage_id>/stream/stop")
def stream_stop(cage_id: int):
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)
    ok, msg = _sender(cage_id).send("STOP_STREAMING")
    if ok:
        _valkey.set(f"cage:{cage_id}:streaming", "0")
        _log.info(f"Cage {cage_id}: stream STOPPED")
    return jsonify({"ok": ok, "msg": msg})


@control_bp.post("/cage/<int:cage_id>/trial/start")
def trial_start(cage_id: int):
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)
    body = request.get_json(force=True) or {}
    ok, msg = _sender(cage_id).send("START_TRIAL:" + json.dumps(body))
    return jsonify({"ok": ok, "msg": msg})


@control_bp.post("/cage/<int:cage_id>/trial/stop")
def trial_stop(cage_id: int):
    if not (1 <= cage_id <= config.N_CAGES):
        abort(404)
    ok, msg = _sender(cage_id).send("STOP_TRIAL")
    return jsonify({"ok": ok, "msg": msg})
