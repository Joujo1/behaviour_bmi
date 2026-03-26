N_CAGES = 12

# UDP: Linux machine listens on 5001–5012
# cage_id is 1-indexed: cage_id 1 = physical cage 1 = port 5001
# formula: UDP_BASE_PORT + cage_id
UDP_BASE_PORT = 5000  # cage_id 1 → 5001, cage_id 12 → 5012

# Pi static IPs: cage 1 → 192.168.1.101, cage 2 → 192.168.1.102, ...
PI_IPS = {cage_id: f"192.168.1.{100 + cage_id}" for cage_id in range(1, N_CAGES + 1)}

# Valkey (Redis-compatible)
VALKEY_HOST = "localhost"
VALKEY_PORT = 6379
VALKEY_FRAME_TTL_SECONDS = 5  # latest_frame key expires if no update for 5s

# PostgreSQL
POSTGRES_DSN = "postgresql://bmi:yaniklab@localhost/bmi_closed_loop"
DB_CHUNK_SIZE = 1000  # commit a recordings row every N frames per camera

# Storage
NAS_BASE_PATH = "/home/sentinel/new_vr/bmi_closed_loop/NAS"
SESSION_DIR = ""  # set at session open, left empty until defined

# Acquisition
FRAME_QUEUE_MAXSIZE = 60  # per-camera write queue depth

# Watchdog
WATCHDOG_INTERVAL_SECONDS = 1
WATCHDOG_DEAD_THRESHOLD_SECONDS = 5  # camera flagged dead if silent for this long

# TCP command channel (PC → Pi)
TCP_COMMAND_PORT = 6000  # Pi listens on this port; one connection per cage

# Flask
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000

# Logging
LOGGING_DIR = "/home/sentinel/new_vr/bmi_closed_loop/logs"
LOGGING_LEVEL = "INFO"
