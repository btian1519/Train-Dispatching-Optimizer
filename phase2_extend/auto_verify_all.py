import os
import sys
import glob
import time
import subprocess
import json
from src.data_parser import DisplibInstance
from src.cp_model import DisplibCPModel

# Configuration
TIME_LIMIT = 30  # Seconds per instance for the "all-run"
DATASET_DIR = os.path.join("..", "dataset", "displib_problems")
OUTPUT_DIR = os.path.join("output")
VERIFIER_PATH = os.path.join("..", "dataset", "displib_verify", "displib_verify.py")
RESULTS_LOG = "verification_results.md"

def run_verification():
    # Ensure output dir exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Get all json files
    problem_files = sorted(glob.glob(os.path.join(DATASET_DIR, "*.json")))
    
    results = []
    
    print(f"Found {len(problem_files)} problem files. Starting batch run...")
    
    for i, prob_file in enumerate(problem_files):
        prob_name = os.path.basename(prob_file)
        sol_file = os.path.join(OUTPUT_DIR, f"solution_{prob_name}")
        
        print(f"\n[{i+1}/{len(problem_files)}] Processing: {prob_name}")
        
        # 1. Solve with CP-SAT
        try:
            instance = DisplibInstance.from_json(prob_file)
            cp_model = DisplibCPModel(instance)
            status = cp_model.optimize(time_limit=TIME_LIMIT)
            
            if status in ["OPTIMAL", "FEASIBLE"]:
                cp_model.export_solution(sol_file)
                solve_status = f"✅ {status}"
            else:
                solve_status = f"❌ {status}"
                results.append({"name": prob_name, "solver": solve_status, "verifier": "N/A", "obj": "N/A"})
                continue
                
        except Exception as e:
            print(f"Error solving {prob_name}: {e}")
            results.append({"name": prob_name, "solver": f"💥 ERROR", "verifier": "N/A", "obj": "N/A"})
            continue

        # 2. Verify with displib_verify.py
        try:
            # We call the verifier script via subprocess
            # Usage: python displib_verify.py PROBLEMFILE SOLUTIONFILE
            cmd = [sys.executable, VERIFIER_PATH, prob_file, sol_file]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()
            
            if "[VERIFIED]" in stdout and "Error verifying" not in stdout:
                verify_status = "✅ VERIFIED"
            else:
                verify_status = "❌ FAILED"
                # If failed, let's keep the error log for debugging
                with open(os.path.join(OUTPUT_DIR, f"error_{prob_name}.log"), "w", encoding='utf-8') as f:
                    f.write(stdout + "\n" + stderr)
            
            results.append({
                "name": prob_name,
                "solver": solve_status,
                "verifier": verify_status,
                "obj": cp_model.obj_val
            })
            print(f"   Result: Solver={solve_status}, Verifier={verify_status}")
            
        except Exception as e:
            print(f"Error verifying {prob_name}: {e}")
            results.append({"name": prob_name, "solver": solve_status, "verifier": "💥 ERROR", "obj": cp_model.obj_val})

    # 3. Generate Report
    with open(RESULTS_LOG, "w", encoding='utf-8') as f:
        f.write("# Verification Results (CP-SAT Model)\n\n")
        f.write(f"Run Date: {time.ctime()}\n")
        f.write(f"Time Limit: {TIME_LIMIT}s per instance\n\n")
        f.write("| Instance | Solver Status | Verifier | Objective |\n")
        f.write("| --- | --- | --- | --- |\n")
        for r in results:
            f.write(f"| {r['name']} | {r['solver']} | {r['verifier']} | {r['obj']} |\n")
            
    print(f"\nBatch run complete. Results written to {RESULTS_LOG}")

if __name__ == "__main__":
    # Change CWD to script directory to ensure relative paths work
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    run_verification()
