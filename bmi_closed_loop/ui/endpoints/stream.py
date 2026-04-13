import valkey as valkey_client
from flask import Blueprint, abort, make_response

import config

stream_bp = Blueprint("stream", __name__)
_valkey = valkey_client.Valkey(host=config.VALKEY_HOST, port=config.VALKEY_PORT)


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


@stream_bp.get("/cameras/status")
def camera_status():
    status = _valkey.hgetall("camera_status")
    return {k.decode(): v.decode() for k, v in status.items()}


@stream_bp.get("/cameras/peripherals")
def cameras_peripherals():
    """Return fan and strip state for all cages."""
    result = {}
    for cage_id in range(1, config.N_CAGES + 1):
        result[cage_id] = {
            "fan":   _valkey.get(f"cage:{cage_id}:fan")   == b"1",
            "strip": _valkey.get(f"cage:{cage_id}:strip") == b"1",
        }
    return result
