import logging

import graphviz
import psycopg2
import psycopg2.extras
from flask import Blueprint, Response, abort, jsonify, render_template, request

import config

curriculum_bp = Blueprint("curriculum", __name__)
_log = logging.getLogger("curriculum")


def _get_db():
    return psycopg2.connect(config.POSTGRES_DSN)


@curriculum_bp.get("/training-stages")
def list_stages():
    """Return all stages with their substages nested, for UI dropdowns."""
    conn = _get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    tst.id, tst.name, tst.description, tst.sort_order,
                    ts.id              AS substage_id,
                    ts.substage_number,
                    ts.label,
                    ts.retired
                FROM training_stages tst
                LEFT JOIN training_substages ts ON ts.stage_id = tst.id
                ORDER BY tst.sort_order, tst.id, ts.substage_number
            """)
            rows = cur.fetchall()
    finally:
        conn.close()

    stages: dict = {}
    for r in rows:
        sid = r[0]
        if sid not in stages:
            stages[sid] = {"id": r[0], "name": r[1], "description": r[2],
                           "sort_order": r[3], "substages": []}
        if r[4] is not None:
            stages[sid]["substages"].append({
                "id": r[4], "substage_number": r[5],
                "label": r[6], "retired": r[7],
            })

    return jsonify(list(stages.values()))


@curriculum_bp.post("/training-stages")
def create_stage():
    """Create a new training stage."""
    body = request.get_json(force=True) or {}
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "msg": "name is required"}), 400

    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO training_stages (name, description, sort_order)
                    VALUES (%s, %s, %s) RETURNING id
                """, (name, body.get("description"), body.get("sort_order", 0)))
                stage_id = cur.fetchone()[0]
    except psycopg2.errors.UniqueViolation:
        return jsonify({"ok": False, "msg": f"stage '{name}' already exists"}), 409
    finally:
        conn.close()

    _log.info("Created training stage '%s' (id=%d)", name, stage_id)
    return jsonify({"ok": True, "id": stage_id})



@curriculum_bp.get("/curriculum")
def curriculum_page():
    return render_template("curriculum.html")


@curriculum_bp.get("/curriculum/graph")
def curriculum_graph():
    """Render the full curriculum as a Graphviz substage-flow SVG."""
    conn = _get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    ts.id, ts.label, ts.substage_number, ts.retired,
                    ts.stage_id, tst.name AS stage_name, tst.sort_order,
                    ts.advance_to_substage_id, ts.fallback_to_substage_id,
                    ts.advance_criteria, ts.fallback_criteria
                FROM training_substages ts
                JOIN training_stages tst ON tst.id = ts.stage_id
                ORDER BY tst.sort_order, tst.id, ts.substage_number
            """)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
    finally:
        conn.close()

    if not rows:
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="40">'
               '<text x="12" y="24" font-family="Helvetica" font-size="12" fill="#888">'
               'No substages yet</text></svg>')
        return Response(svg, mimetype="image/svg+xml")

    substages = [dict(zip(cols, r)) for r in rows]

    # Group by stage for cluster subgraphs
    stages: dict = {}
    for s in substages:
        sid = s["stage_id"]
        if sid not in stages:
            stages[sid] = {"name": s["stage_name"], "sort_order": s["sort_order"], "substages": []}
        stages[sid]["substages"].append(s)

    dot = graphviz.Digraph(
        graph_attr={"rankdir": "LR", "bgcolor": "transparent", "pad": "0.5",
                    "nodesep": "0.6", "ranksep": "1.2"},
        node_attr={"fontname": "Helvetica", "fontsize": "14"},
        edge_attr={"fontname": "Helvetica", "fontsize": "11"},
    )

    sub_ids = {s["id"] for s in substages}

    for stage_id, stage in sorted(stages.items(), key=lambda x: x[1]["sort_order"]):
        with dot.subgraph(name=f"cluster_{stage_id}") as c:
            c.attr(label=stage["name"], style="rounded", color="#cccccc",
                   fontname="Helvetica", fontsize="13", fontcolor="#888888")
            for sub in stage["substages"]:
                node_id = f"s{sub['id']}"
                label = f"{sub['substage_number']}. {sub['label']}"
                if sub["retired"]:
                    c.node(node_id, label, shape="rectangle", style="rounded,filled",
                           fillcolor="#f0f0f0", color="#aaaaaa", fontcolor="#aaaaaa")
                else:
                    c.node(node_id, label, shape="rectangle", style="rounded,filled",
                           fillcolor="white", color="black")

    for sub in substages:
        src = f"s{sub['id']}"

        adv_id = sub["advance_to_substage_id"]
        if adv_id and adv_id in sub_ids:
            ac = sub["advance_criteria"] or {}
            if ac.get("window") and ac.get("threshold") is not None:
                edge_label = f"≥{round(ac['threshold'] * 100)}% / {ac['window']} trials"
            else:
                edge_label = "advance"
            dot.edge(src, f"s{adv_id}", label=edge_label,
                     color="#40ca72", fontcolor="#40ca72")

        fall_id = sub["fallback_to_substage_id"]
        if fall_id and fall_id in sub_ids:
            fc = sub["fallback_criteria"] or {}
            if fc.get("window") and fc.get("threshold") is not None:
                edge_label = f"≤{round(fc['threshold'] * 100)}% / {fc['window']} trials"
            else:
                edge_label = "fallback"
            dot.edge(src, f"s{fall_id}", label=edge_label,
                     color="#cd1414", fontcolor="#cd1414", style="dashed")

    svg = dot.pipe(format="svg").decode("utf-8")
    return Response(svg, mimetype="image/svg+xml")


@curriculum_bp.get("/training-substages/<int:substage_id>")
def get_substage(substage_id: int):
    """Return full detail for a single substage including task_config and criteria."""
    conn = _get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    ts.id, ts.stage_id, ts.substage_number, ts.label,
                    ts.task_config,
                    ts.advance_criteria, ts.fallback_criteria,
                    ts.advance_to_substage_id, ts.fallback_to_substage_id,
                    ts.retired,
                    tst.name AS stage_name
                FROM training_substages ts
                JOIN training_stages tst ON tst.id = ts.stage_id
                WHERE ts.id = %s
            """, (substage_id,))
            row = cur.fetchone()
            if row is None:
                abort(404)
            cols = [d[0] for d in cur.description]
    finally:
        conn.close()
    return jsonify(dict(zip(cols, row)))


@curriculum_bp.post("/training-substages")
def create_substage():
    """Create a new substage under a stage."""
    body = request.get_json(force=True) or {}
    stage_id = body.get("stage_id")
    label    = (body.get("label") or "").strip()
    if not stage_id or not label:
        return jsonify({"ok": False, "msg": "stage_id and label are required"}), 400

    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO training_substages
                        (stage_id, substage_number, label, task_config,
                         advance_criteria, fallback_criteria,
                         advance_to_substage_id, fallback_to_substage_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    stage_id,
                    body.get("substage_number", 1),
                    label,
                    psycopg2.extras.Json(body.get("task_config", {})),
                    psycopg2.extras.Json(body.get("advance_criteria"))
                        if body.get("advance_criteria") else None,
                    psycopg2.extras.Json(body.get("fallback_criteria"))
                        if body.get("fallback_criteria") else None,
                    body.get("advance_to_substage_id"),
                    body.get("fallback_to_substage_id"),
                ))
                substage_id = cur.fetchone()[0]
    finally:
        conn.close()

    _log.info("Created substage '%s' (id=%d) under stage %d", label, substage_id, stage_id)
    return jsonify({"ok": True, "id": substage_id})


@curriculum_bp.patch("/training-substages/<int:substage_id>")
def update_substage(substage_id: int):
    """Update an existing substage (task_config, criteria, advance/fallback links)."""
    body = request.get_json(force=True) or {}

    fields = []
    values = []

    if "label" in body:
        fields.append("label = %s"); values.append(body["label"])
    if "task_config" in body:
        fields.append("task_config = %s")
        values.append(psycopg2.extras.Json(body["task_config"]))
    if "advance_criteria" in body:
        fields.append("advance_criteria = %s")
        values.append(psycopg2.extras.Json(body["advance_criteria"])
                      if body["advance_criteria"] else None)
    if "fallback_criteria" in body:
        fields.append("fallback_criteria = %s")
        values.append(psycopg2.extras.Json(body["fallback_criteria"])
                      if body["fallback_criteria"] else None)
    if "advance_to_substage_id" in body:
        fields.append("advance_to_substage_id = %s")
        values.append(body["advance_to_substage_id"])
    if "fallback_to_substage_id" in body:
        fields.append("fallback_to_substage_id = %s")
        values.append(body["fallback_to_substage_id"])
    if "retired" in body:
        fields.append("retired = %s"); values.append(bool(body["retired"]))

    if not fields:
        return jsonify({"ok": False, "msg": "nothing to update"}), 400

    values.append(substage_id)
    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE training_substages SET {', '.join(fields)} WHERE id = %s RETURNING id",
                    values,
                )
                if cur.fetchone() is None:
                    abort(404)
    finally:
        conn.close()

    return jsonify({"ok": True})


@curriculum_bp.delete("/training-substages/<int:substage_id>")
def delete_substage(substage_id: int):
    """Permanently delete a substage. Fails if any trial_results reference it."""
    conn = _get_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM trial_results WHERE substage_id = %s",
                    (substage_id,),
                )
                if cur.fetchone()[0] > 0:
                    return jsonify({
                        "ok": False,
                        "msg": "Cannot delete: substage has trial results. Retire it instead.",
                    }), 409
                cur.execute(
                    "DELETE FROM training_substages WHERE id = %s RETURNING id",
                    (substage_id,),
                )
                if cur.fetchone() is None:
                    abort(404)
    finally:
        conn.close()

    _log.info("Deleted substage id=%d", substage_id)
    return jsonify({"ok": True})
