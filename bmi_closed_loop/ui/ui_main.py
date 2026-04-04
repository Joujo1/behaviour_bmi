import logging
import config
from command.tcp_command_sender import TCPCommandSender
from flask import Flask, render_template
from ui.endpoints.builder import builder_bp
from ui.endpoints.control import control_bp
from ui.endpoints.dev import dev_bp
from ui.endpoints.session import session_bp
from ui.endpoints.stream import stream_bp
from ui.endpoints.trial import trial_bp, handle_trial_event

app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

_log = logging.getLogger("ui_main")


def _on_pi_event(cage_id: int, event: dict) -> None:
    try:
        handle_trial_event(cage_id, event)
    except Exception as e:
        _log.error("Unhandled error in Pi event handler (cage %d): %s", cage_id, e)


app.config["COMMAND_SENDERS"] = {
    cage_id: TCPCommandSender(
        cage_id=cage_id,
        host=config.PI_IPS[cage_id],
        port=config.TCP_COMMAND_PORT,
        on_event=_on_pi_event,
    )
    for cage_id in range(1, config.N_CAGES + 1)
}

app.register_blueprint(builder_bp)
app.register_blueprint(dev_bp)
app.register_blueprint(stream_bp)
app.register_blueprint(trial_bp)
app.register_blueprint(session_bp)
app.register_blueprint(control_bp)


@app.get("/")
def dashboard():
    return render_template("index.html", n_cages=config.N_CAGES)


if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT)
