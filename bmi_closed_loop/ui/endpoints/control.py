import logging

import graphviz
import valkey as valkey_client
from flask import Blueprint, Response, abort, jsonify, request, current_app

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


@control_bp.post("/trial/graph")
def trial_graph():
    """Render a trial JSON definition as a Graphviz state machine SVG."""
    body = request.get_json(force=True) or {}

    dot = graphviz.Digraph(
        graph_attr={"rankdir": "LR", "bgcolor": "transparent", "pad": "0.3"},
        node_attr={"fontname": "Helvetica", "fontsize": "11"},
        edge_attr={"fontname": "Helvetica", "fontsize": "10"},
    )

    dot.node("__start__", "", shape="point", width="0.2")
    initial = body.get("initial_state", "")
    if initial:
        dot.edge("__start__", initial)

    end_added = set()
    for state in body.get("states", []):
        sid = state["id"]

        # Build a Stateflow-style label: state name, then entry/exit action lines
        label = sid
        entry = state.get("entry_actions", [])
        exit_ = state.get("exit_actions", [])
        if entry or exit_:
            label += "\\l│"
            for a in entry:
                if a.get("type") == "play_clicks":
                    label += (f"\\lentry: play_clicks("
                              f"L={a.get('left_rate','?')} R={a.get('right_rate','?')} "
                              f"dur={a.get('click_duration','?')}s)")
                else:
                    label += f"\\lentry: {a['type']}({a.get('target', '')})"
            for a in exit_:
                if a.get("type") == "play_clicks":
                    label += (f"\\lexit:  play_clicks("
                              f"L={a.get('left_rate','?')} R={a.get('right_rate','?')} "
                              f"dur={a.get('click_duration','?')}s)")
                else:
                    label += f"\\lexit:  {a['type']}({a.get('target', '')})"
            label += "\\l"   # trailing newline keeps text left-aligned

        dot.node(sid, label, shape="rectangle", style="rounded")

        for t in state.get("transitions", []):
            next_s = t.get("next_state", "")
            trigger = t.get("trigger", "")

            if trigger == "beam_break":
                hold_ms = t.get("hold_ms")
                hold_str = f" hold {hold_ms:.0f}ms" if hold_ms else ""
                label = f"beam / {t.get('target', '')}{hold_str}"
            elif trigger == "timeout":
                dur = state.get("duration")
                label = f"timeout {dur}s" if dur is not None else "timeout"
            elif trigger == "clicks_done":
                label = "clicks done"
            else:
                label = trigger

            TERMINALS = {
                "__end__":     ("black",     "black"),
                "__correct__": ("#40ca72",   "#40ca72"),
                "__wrong__":   ("#cd1414",   "#cd1414"),
            }
            if next_s in TERMINALS:
                if next_s not in end_added:
                    color, fill = TERMINALS[next_s]
                    dot.node(next_s, "", shape="doublecircle", width="0.25",
                             style="filled", fillcolor=fill, color=color)
                    end_added.add(next_s)
                dot.edge(sid, next_s, label=label)
            else:
                dot.edge(sid, next_s, label=label)

    svg = dot.pipe(format="svg").decode("utf-8")
    return Response(svg, mimetype="image/svg+xml")
