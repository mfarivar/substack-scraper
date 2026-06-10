import os
import shutil
import subprocess

def create_dmg():
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(workspace_dir, "dist")
    app_path = os.path.join(dist_dir, "StackFlow.app")
    
    # 1. Check if the app is built
    if not os.path.exists(app_path):
        print(f"Error: Could not find {app_path}. Please build the app first.")
        return
        
    print("Preparing to create DMG...")
    
    # 2. Set up temporary directory for DMG contents
    tmp_dmg_dir = os.path.join(workspace_dir, "dmg_temp")
    if os.path.exists(tmp_dmg_dir):
        shutil.rmtree(tmp_dmg_dir)
    os.makedirs(tmp_dmg_dir)
    
    # 3. Copy the app bundle
    target_app_path = os.path.join(tmp_dmg_dir, "StackFlow.app")
    print("Copying App bundle...")
    shutil.copytree(app_path, target_app_path, symlinks=True)
    
    # 4. Create a symbolic link to /Applications
    print("Creating shortcut to /Applications...")
    applications_symlink = os.path.join(tmp_dmg_dir, "Applications")
    try:
        os.symlink("/Applications", applications_symlink)
    except Exception as e:
        print("Failed to create symlink natively, attempting terminal shell execution...")
        subprocess.run(["ln", "-s", "/Applications", applications_symlink])
        
    # 5. Build the DMG file using macOS hdiutil
    dmg_output_path = os.path.join(dist_dir, "StackFlow.dmg")
    if os.path.exists(dmg_output_path):
        os.remove(dmg_output_path)
        
    print("Generating DMG file...")
    cmd = [
        "hdiutil", "create",
        "-volname", "StackFlow Installer",
        "-srcfolder", tmp_dmg_dir,
        "-ov",
        "-format", "UDZO",
        dmg_output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # 6. Cleanup
    print("Cleaning up temporary build files...")
    shutil.rmtree(tmp_dmg_dir)
    
    if result.returncode == 0:
        print(f"\nSuccess! DMG created at: {dmg_output_path}")
    else:
        print(f"\nError creating DMG: {result.stderr}")

if __name__ == "__main__":
    create_dmg()
