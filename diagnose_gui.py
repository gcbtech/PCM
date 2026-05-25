import os
import sys
import time
import threading

def run_gui_diagnostics():
    print("PCM (PC Mover) - GUI Thread Diagnostic Harness")
    print("===============================================")
    
    # 1. Import customtkinter and verify
    try:
        import customtkinter as ctk
        print("[OK] CustomTkinter imported successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to import customtkinter: {e}")
        return

    # 2. Import PCM modules
    try:
        from gui.app import PCMApp
        import scanner
        print("[OK] PCM modules imported successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to import PCM modules: {e}")
        return

    # Initialize app in export mode
    print("\n3. Initializing PCMApp in export mode...")
    app = None
    try:
        app = PCMApp(mode="export")
        print("[OK] PCMApp initialized.")
    except Exception as e:
        print(f"[ERROR] Failed to initialize PCMApp: {e}")
        import traceback
        traceback.print_exc()
        return

    # Check state
    print(f"  - Mode: {app.mode}")
    print(f"  - Detected User Profiles count: {len(app.user_profiles)}")
    if app.user_profiles:
        for idx, p in enumerate(app.user_profiles):
            print(f"    Profile {idx}: {p.username} ({p.path})")
    print(f"  - Selected Profile: {app.selected_profile.username if app.selected_profile else 'None'}")

    # 4. Simulate clicking "Scan My Files"
    print("\n4. Simulating click on 'Scan My Files'...")
    
    # We will temporarily mock the thread end transition to close the app after it finishes!
    original_results_screen = None
    
    def mock_results_screen(self):
        print("\n[OK] Transitioned to show_scan_results_screen successfully!")
        print("Diagnostic test completed successfully! Closing app.")
        app.quit()

    # Apply the mock to capture transition completion
    import gui.export_view
    original_results_screen = gui.export_view.show_scan_results_screen
    gui.export_view.show_scan_results_screen = mock_results_screen

    # Safely trigger transition
    print("Calling proceed_to_scan via welcome screen trigger...")
    from gui.export_view import show_scanning_loading_screen
    
    # Let's run the loading screen which spawns the thread
    show_scanning_loading_screen(app)
    
    # Since we are running in the main thread, we must start the tkinter mainloop 
    # so the thread callbacks and idle updates can process!
    # We'll set a safety timer to quit the mainloop if it hangs!
    def watchdog():
        time.sleep(5)
        print("\n[WATCHDOG WARNING] Execution did not finish in 5 seconds. App might be hung.")
        print("Closing event loop for inspection.")
        app.quit()
        
    threading.Thread(target=watchdog, daemon=True).start()
    
    print("Starting CustomTkinter event loop...")
    app.mainloop()
    print("Event loop closed.")

if __name__ == "__main__":
    run_gui_diagnostics()
