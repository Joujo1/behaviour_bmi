import logging
import config
import valkey as valkey_client
from command.tcp_command_sender import TCPCommandSender
from flask import Flask, render_template
from ui.cage_runner import CageRunner, runners
from ui.endpoints.builder import builder_bp
from ui.endpoints.control import control_bp
from ui.endpoints.dev import dev_bp
from ui.endpoints.session import session_bp
from ui.endpoints.subjects import subjects_bp
from ui.endpoints.curriculum import curriculum_bp
from ui.endpoints.stream import stream_bp
from ui.endpoints.metrics import metrics_bp
from ui.endpoints.scoresheet import scoresheet_bp
from ui.endpoints.trial import trial_bp
from ui.event_handler import handle_trial_event

app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

# Clear stale streaming state from previous sessions
_valkey = valkey_client.Valkey(host=config.VALKEY_HOST, port=config.VALKEY_PORT)
for _cage_id in range(1, config.N_CAGES + 1):
    _valkey.set(f"cage:{_cage_id}:streaming",       "0")
    _valkey.set(f"cage:{_cage_id}:recording",       "0")
    _valkey.set(f"cage:{_cage_id}:fan",             "0")
    _valkey.set(f"cage:{_cage_id}:strip",           "0")
    _valkey.delete(f"cage:{_cage_id}:active_session")

app.config["COMMAND_SENDERS"] = {
    cage_id: TCPCommandSender(
        cage_id=cage_id,
        host=config.PI_IPS[cage_id],
        port=config.TCP_COMMAND_PORT,
        on_event=handle_trial_event,
    )
    for cage_id in range(1, config.N_CAGES + 1)
}

# One CageRunner per cage — permanent, episodic run threads start/stop inside.
for _cage_id in range(1, config.N_CAGES + 1):
    runners[_cage_id] = CageRunner(_cage_id)

app.register_blueprint(metrics_bp)
app.register_blueprint(scoresheet_bp)
app.register_blueprint(builder_bp)
app.register_blueprint(dev_bp)
app.register_blueprint(stream_bp)
app.register_blueprint(trial_bp)
app.register_blueprint(session_bp)
app.register_blueprint(subjects_bp)
app.register_blueprint(curriculum_bp)
app.register_blueprint(control_bp)


@app.get("/")
def dashboard():
    return render_template("index.html", n_cages=config.N_CAGES,
                           fan_min_duty=config.FAN_MIN_DUTY)


if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT)
