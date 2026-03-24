import config
from flask import Flask
from ui.endpoints.session import session_bp
from ui.endpoints.stream import stream_bp
from ui.endpoints.trial import trial_bp

app = Flask(__name__)
app.register_blueprint(stream_bp)
app.register_blueprint(trial_bp)
app.register_blueprint(session_bp)

if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT)
