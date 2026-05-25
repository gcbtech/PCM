import os
import sys
import time
import traceback

def run_diagnostics():
    print("PCM (PC Mover) - Diagnostic Test Runner")
    print("=======================================")
    print(f"System: {sys.platform}")
    print(f"Python: {sys.version}")
    
    # Import scanner directly
    try:
        import scanner
        print("[OK] Successfully imported scanner module.")
    except Exception as e:
        print(f"[ERROR] Failed to import scanner: {e}")
        traceback.print_exc()
        return

    print("\n1. Scanning Local User Profiles...")
    try:
        profiles = scanner.scan_user_profiles()
        print(f"[OK] Found {len(profiles)} user profiles:")
        for p in profiles:
            print(f"  - {p.username} (Path: {p.path})")
            
        if not profiles:
            print("[ERROR] No user profiles found!")
            return
            
        # Select target profile (first active profile)
        target_profile = profiles[0]
        print(f"\n2. Initializing scan for: {target_profile.username} (Path: {target_profile.path})...")
        
        # Test status callback to show progress in terminal
        def status_cb(msg):
            print(f"  [STATUS CALLBACK] {msg}")
            sys.stdout.flush()
            
        print("Running scan_profile_folders...")
        start_time = time.time()
        folders = scanner.scan_profile_folders(target_profile.path, status_callback=status_cb)
        elapsed = time.time() - start_time
        
        print(f"\n[OK] scan_profile_folders finished in {elapsed:.3f} seconds.")
        print("\nScan Results:")
        for name, info in folders.items():
            if info.exists:
                print(f"  - {name}: {info.file_count} files, {info.get_friendly_size()}")
            else:
                print(f"  - {name}: (does not exist)")
                
        print("\n=======================================")
        print("[OK] DIAGNOSTICS COMPLETED SUCCESSFULLY!")
        print("=======================================")
        
    except Exception as e:
        print("\n[ERROR] DIAGNOSTIC FAILED WITH EXCEPTION:")
        traceback.print_exc()

if __name__ == "__main__":
    run_diagnostics()
