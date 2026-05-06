import os
import shutil
import glob

# --- CONFIGURATION ---
# Files we NEVER want to move (Critical to the app)
CRITICAL_FILES = [
    "dashboard.py",
    "get_deals.py",
    "run.py",
    "classifier.py",
    "ai_quality_analyzer.py",
    "verify_flyers.py",
    "cleanup.py",
    ".env",
    "requirements.txt",
    # Main Data Files
    "seton_grocery_history.csv",
    "historical_archive.csv",
    "current_flyers.csv",
    "clean_grocery_data.csv", 
]

# Patterns to keep in root (e.g., StatsCan data usually starts with 1810)
KEEP_PATTERNS = ["1810*.csv", "*history.csv"]

# Where to move things
STRUCTURE = {
    "flyers": [".pdf"],                 # All flyer PDFs
    "images": [".jpg", ".jpeg", ".png"], # Temp OCR images
    "logs": [".log", ".txt"],           # Log files (careful with requirements.txt)
    "archive": [],                      # Old/Backup CSVs
    "build_artifacts": [".spec"]        # PyInstaller specs
}

def matches_keep_pattern(filename):
    for pattern in KEEP_PATTERNS:
        if glob.fnmatch.fnmatch(filename, pattern):
            return True
    return False

def organize_project():
    print("🧹 Starting Project Cleanup...")
    
    # 1. Create Directories
    for folder in STRUCTURE.keys():
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"   Created folder: {folder}/")

    # 2. Loop through all files in current dir
    files = [f for f in os.listdir('.') if os.path.isfile(f)]
    
    moved_count = 0
    
    for f in files:
        # Skip critical files
        if f in CRITICAL_FILES or matches_keep_pattern(f):
            continue
            
        file_ext = os.path.splitext(f)[1].lower()
        
        # Move PDFs (Flyers)
        if file_ext in STRUCTURE["flyers"]:
            shutil.move(f, os.path.join("flyers", f))
            print(f"   📂 Moved flyer: {f} -> flyers/")
            moved_count += 1
            
        # Move Images
        elif file_ext in STRUCTURE["images"]:
            shutil.move(f, os.path.join("images", f))
            print(f"   🖼️  Moved image: {f} -> images/")
            moved_count += 1
            
        # Move Logs (Skip requirements.txt and config.txt)
        elif file_ext in STRUCTURE["logs"] and "requirements" not in f and "config" not in f:
            shutil.move(f, os.path.join("logs", f))
            print(f"   📝 Moved log: {f} -> logs/")
            moved_count += 1
            
        # Move PyInstaller Specs
        elif file_ext in STRUCTURE["build_artifacts"]:
            shutil.move(f, os.path.join("build_artifacts", f))
            print(f"   📦 Moved spec: {f} -> build_artifacts/")
            moved_count += 1

    # 3. Clean up PyInstaller Folders (dist/build) if they exist
    # (Optional: ask user first, or just do it if they want clean root)
    if os.path.exists("build"):
        shutil.rmtree("build")
        print("   🗑️  Removed 'build' folder")
        
    if os.path.exists("__pycache__"):
        shutil.rmtree("__pycache__")
        print("   🗑️  Removed '__pycache__' folder")

    print(f"\n✨ Cleanup Complete! Moved {moved_count} files.")
    print("   Your PDFs are now in the 'flyers/' folder.")

if __name__ == "__main__":
    organize_project()