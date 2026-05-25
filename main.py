import os
import sys

# Redirect standard stdout/stderr to devnull in frozen mode to avoid PyInstaller --noconsole print errors/locks
if getattr(sys, 'frozen', False):
    try:
        f = open(os.devnull, 'w')
        sys.stdout = f
        sys.stderr = f
    except Exception:
        pass

import manifest
from gui.app import PCMApp

def main():
    # Detect running folder to look for manifest.json
    running_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    
    # Auto-detection
    # If manifest.json is found next to the executable, we default to Import Mode.
    # Otherwise, we default to Export Mode.
    mode = "export"
    if manifest.is_pcm_drive(running_dir):
        mode = "import"
    else:
        # Also check the parent directory in case we are run from a subfolder
        parent_dir = os.path.dirname(running_dir)
        if manifest.is_pcm_drive(parent_dir):
            mode = "import"

    print(f"PCM (PC Mover) initialized in [{mode.upper()}] mode.")
    print(f"Running directory: {running_dir}")

    # Launch GUI
    app = PCMApp(mode=mode)
    app.mainloop()

if __name__ == "__main__":
    main()
