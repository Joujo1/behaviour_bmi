import json

from flask import Blueprint, abort, jsonify, request, current_app

import config

control_bp = Blueprint("control", __name__)


def _sender(cage_id: int):
    senders = current_app.config.get("COMMAND_SENDERS", {})
    sender = senders.get(cage_id)
    if sender is None:
        abort(404)
    return sender


@control_bp.post("/cage/<int:cage_id>/stream/start")
def stream_start(cage_id: int):
    if not (0 <= cage_id < config.N_CAGES):
        abort(404)
    ok, msg = _sender(cage_id).send("START_STREAMING")
    return jsonify({"ok": ok, "msg": msg})


@control_bp.post("/cage/<int:cage_id>/stream/stop")
def stream_stop(cage_id: int):
    if not (0 <= cage_id < config.N_CAGES):
        abort(404)
    ok, msg = _sender(cage_id).send("STOP_STREAMING")
    return jsonify({"ok": ok, "msg": msg})


@control_bp.post("/cage/<int:cage_id>/trial/start")
def trial_start(cage_id: int):
    if not (0 <= cage_id < config.N_CAGES):
        abort(404)
    body = request.get_json(force=True) or {}
    ok, msg = _sender(cage_id).send("START_TRIAL:" + json.dumps(body))
    return jsonify({"ok": ok, "msg": msg})


@control_bp.post("/cage/<int:cage_id>/trial/stop")
def trial_stop(cage_id: int):
    if not (0 <= cage_id < config.N_CAGES):
        abort(404)
    ok, msg = _sender(cage_id).send("STOP_TRIAL")
    return jsonify({"ok": ok, "msg": msg})
