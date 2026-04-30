import os

N_CAGES = 12

# formula: UDP_BASE_PORT + cage_id
UDP_BASE_PORT = 5000  # cage_id 1 → 5001, cage_id 12 → 5012

PI_IPS = {cage_id: f"192.168.1.{100 + cage_id}" for cage_id in range(1, N_CAGES + 1)}

VALKEY_HOST = "localhost"
VALKEY_PORT = 6379
VALKEY_FRAME_TTL_SECONDS = 5

POSTGRES_DSN = "postgresql://bmi:yaniklab@localhost/bmi_closed_loop"
DB_CHUNK_SIZE = 1000

NAS_BASE_PATH = "/home/sentinel/Desktop/bmi/behaviour_bmi/bmi_closed_loop/NAS"
SESSION_DIR = ""  # set at session open

FRAME_QUEUE_MAXSIZE = 60

WATCHDOG_INTERVAL_SECONDS = 1
WATCHDOG_DEAD_THRESHOLD_SECONDS = 10

RECORDING_CHECK_INTERVAL_S = 1.0
TRIAL_TIMEOUT_S = 1230

TCP_COMMAND_PORT = 6000

FAN_MIN_DUTY = 30

FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000

CLICK_WIDTH_S = 0.003   # seconds — must match CLICK_WIDTH_S in RPi_main/config.py

LOGGING_DIR = os.environ.get(
    "BMI_LOG_DIR",
    "/home/sentinel/Desktop/bmi/behaviour_bmi/bmi_closed_loop/logs"
)
LOGGING_LEVEL = "INFO"

SCORESHEET_TEMPLATE_PATH = "/home/sentinel/Desktop/bmi/behaviour_bmi/bmi_closed_loop/Scoresheet_Sample.xlsx"
