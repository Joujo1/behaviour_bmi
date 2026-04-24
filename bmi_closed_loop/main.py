import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

RUN_DURATION_S = 4 * 3600  # 4 hours


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <session_name> [duration_hours]")
        print("Example: python main.py joel_2024_03_25")
        print("         python main.py joel_2024_03_25 2.5")
        sys.exit(1)

    session_name = sys.argv[1]
    duration_s = float(sys.argv[2]) * 3600 if len(sys.argv) > 2 else RUN_DURATION_S

    procs = {}

    import config
    session_dir = os.path.join(config.NAS_BASE_PATH, session_name)

    log_dir = os.path.join(
        "/home/sentinel/Desktop/bmi/behaviour_bmi/bmi_closed_loop/logs",
        f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_{session_name}",
    )
    os.makedirs(log_dir, exist_ok=True)
    env = {**os.environ, "BMI_LOG_DIR": log_dir}

    procs["acquisition"] = subprocess.Popen(
        [sys.executable, "-m", "acquisition.acquisition_main", session_name],
        cwd=PROJECT_ROOT, env=env,
    )
    procs["ui"] = subprocess.Popen(
        [sys.executable, "-m", "ui.ui_main"],
        cwd=PROJECT_ROOT, env=env,
    )
    deadline = time.time() + duration_s
    h = int(duration_s // 3600)
    m = int((duration_s % 3600) // 60)
    print(f"\n  Session  : {session_name}")
    print(f"  UI       : http://localhost:5000")
    print(f"  Auto-stop: {h}h{m:02d}m  (Ctrl-C to stop earlier)\n")

    def _timer():
        remaining = deadline - time.time()
        if remaining > 0:
            time.sleep(remaining)
        print(f"\n[main] Timer elapsed — shutting down after {h}h{m:02d}m")
        os.kill(os.getpid(), signal.SIGTERM)

    timer = threading.Thread(target=_timer, daemon=True, name="shutdown-timer")
    timer.start()

    def shutdown(sig, frame):
        print("\nShutting down...")
        for name, p in procs.items():
            p.terminate()
        for name, p in procs.items():
            p.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        for name, p in procs.items():
            if p.poll() is not None:
                print(f"[main] Process '{name}' exited with code {p.returncode}")
        time.sleep(1)


if __name__ == "__main__":
    main()
