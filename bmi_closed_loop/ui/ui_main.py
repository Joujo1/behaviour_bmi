import config
from command.tcp_command_sender import TCPCommandSender
from flask import Flask, render_template
from ui.endpoints.control import control_bp
from ui.endpoints.session import session_bp
from ui.endpoints.stream import stream_bp
from ui.endpoints.trial import trial_bp

app = Flask(__name__)

app.config["COMMAND_SENDERS"] = {
    cage_id: TCPCommandSender(
        cage_id=cage_id,
        host=config.PI_IPS[cage_id],
        port=config.TCP_COMMAND_PORT,
    )
    for cage_id in range(config.N_CAGES)
}

app.register_blueprint(stream_bp)
app.register_blueprint(trial_bp)
app.register_blueprint(session_bp)
app.register_blueprint(control_bp)


@app.get("/")
def dashboard():
    return render_template("index.html", n_cages=config.N_CAGES)


if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT)
