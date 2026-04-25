import os
import time
from src.data_parser import DisplibInstance
from src.mip_model import DisplibMipModel
from gurobipy import GRB

def solve_instance(file_path):
    print(f"\n========================================================")
    print(f"Testing Real World Data: {os.path.basename(file_path)}")
    print(f"========================================================")
    
    if not os.path.exists(file_path):
        print(f"Error: Could not find {file_path}")
        return

    instance = DisplibInstance.from_json(file_path)
    print(f"-> Data Loaded: {len(instance.trains)} Trains, {len(instance.find_conflict_pairs())} Resource Conflicts.")
    
    start_time = time.time()
    mip_model = DisplibMipModel(instance, M=1000000)
    print(f"-> Mathematical constraints built in {time.time() - start_time:.2f} seconds.")
    
    # Turn ON Gurobi Console output (OutputFlag=1) so we can see its progress
    mip_model.model.setParam('OutputFlag', 1) 
    
    # Time limit set to 3 minutes for benchmarking
    print(f"-> Launching Gurobi Optimizer (Time Limit: 180s)...")
    mip_model.optimize(time_limit=180)
    
    print(f"\n====================== RESULTS ========================")
    status = mip_model.model.status
    if status == GRB.OPTIMAL:
        print(f"Status: OPTIMAL! (Objective Value: {mip_model.model.ObjVal})")
    elif status == GRB.TIME_LIMIT:
        print(f"Status: TIME LIMIT REACHED")
        if mip_model.model.SolCount > 0:
            print(f"-> Found feasible sub-optimal solution. Best ObjVal: {mip_model.model.ObjVal}")
        else:
            print("-> FAIL: No feasible solution found before timeout.")
    else:
        print(f"Status: INTERRUPTED or OTHER (Code: {status})")

if __name__ == "__main__":
    # We will pick a small real-world instance from Siemens Mobility Italy (smi)
    # File size is around 11 KB
    script_dir = os.path.dirname(os.path.abspath(__file__))
    target_file = os.path.join(script_dir, "..", "dataset", "displib_problems", "smi_close_4.json")
    solve_instance(target_file)
