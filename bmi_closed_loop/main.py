import os
import signal
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    procs = {}

    procs["acquisition"] = subprocess.Popen(
        [sys.executable, "-m", "acquisition.acquisition_main"],
        cwd=PROJECT_ROOT,
    )
    procs["ui"] = subprocess.Popen(
        [sys.executable, "-m", "ui.ui_main"],
        cwd=PROJECT_ROOT,
    )

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
