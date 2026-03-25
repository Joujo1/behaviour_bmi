import os
import signal
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <session_name>")
        print("Example: python main.py joel_2024_03_25")
        sys.exit(1)

    session_name = sys.argv[1]

    procs = {}

    procs["acquisition"] = subprocess.Popen(
        [sys.executable, "-m", "acquisition.acquisition_main", session_name],
        cwd=PROJECT_ROOT,
    )
    procs["ui"] = subprocess.Popen(
        [sys.executable, "-m", "ui.ui_main"],
        cwd=PROJECT_ROOT,
    )

    print(f"\n  Session : {session_name}")
    print(f"  UI      : http://localhost:5000\n")

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
