import subprocess
from pathlib import Path
import sys

def build_all():
    scripts = [
        "build_periodic_change.py",
        "build_cross_source.py",
        "build_precious_metals.py",
        "build_evidence.py",
        "build_finturk_credit_quality.py",
        "build_duckdb_views.py"
    ]
    
    current_dir = Path(__file__).parent
    
    for script in scripts:
        print(f"================ Running {script} ================")
        script_path = current_dir / script
        result = subprocess.run([sys.executable, str(script_path)])
        if result.returncode != 0:
            print(f"Error running {script}. Exiting.")
            sys.exit(result.returncode)
            
    print("All Gold builders completed successfully.")

if __name__ == "__main__":
    build_all()
