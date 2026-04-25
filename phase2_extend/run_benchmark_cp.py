import os
import time
from src.data_parser import DisplibInstance
from src.cp_model import DisplibCPModel

def solve_instance(file_path):
    print(f"\n========================================================")
    print(f"Testing Real World Data on CP-SAT: {os.path.basename(file_path)}")
    print(f"========================================================")
    
    if not os.path.exists(file_path):
        print(f"Error: Could not find {file_path}")
        return

    instance = DisplibInstance.from_json(file_path)
    print(f"-> Data Loaded: {len(instance.trains)} Trains, {len(instance.find_conflict_pairs())} Resource Conflicts.")
    
    start_time = time.time()
    cp_model = DisplibCPModel(instance)
    print(f"-> CP Model built in {time.time() - start_time:.2f} seconds.")
    
    print(f"-> Launching Google OR-Tools Optimizer (Time Limit: 180s)...")
    status = cp_model.optimize(time_limit=180)
    
    print(f"\n====================== RESULTS ========================")
    if status in ["OPTIMAL", "FEASIBLE"]:
        print(f"Status: {status}! (Objective Value: {cp_model.obj_val})")
    else:
        print(f"Status: {status}")

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    target_file = os.path.join(script_dir, "..", "dataset", "displib_problems", "smi_close_4.json")
    solve_instance(target_file)
