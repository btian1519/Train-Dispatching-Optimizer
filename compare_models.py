import os
import sys
import time

# Add both phase directories to path so we can import them safely
sys.path.append(os.path.abspath("phase1_baseline"))
sys.path.append(os.path.abspath("phase2_extend"))

from phase1_baseline.src.data_parser import DisplibInstance as MIPInstance
from phase1_baseline.src.mip_model import DisplibMipModel
from gurobipy import GRB

from phase2_extend.src.data_parser import DisplibInstance as CPInstance
from phase2_extend.src.cp_model import DisplibCPModel

problem_file = "dataset/displib_instances_testing/displib_instances_testing/displib_testinstances_swapping2.json"
TIME_LIMIT = 60 # Set to 60 seconds to get a quick comparison

print(f"Comparing Models on Dataset: {problem_file} (Time Limit: {TIME_LIMIT}s)\n")
print("=" * 60)

# --------------------------
# 1. Gurobi MIP Model
# --------------------------
print(">>> [Gurobi MIP Model]")
t0 = time.time()
mip_instance = MIPInstance.from_json(problem_file)
t1 = time.time()

t2 = time.time()
mip_model = DisplibMipModel(mip_instance, M=1000000)
mip_model.model.setParam('OutputFlag', 0)
mip_build_time = time.time() - t2

t3 = time.time()
mip_model.optimize(time_limit=TIME_LIMIT)
mip_solve_time = time.time() - t3

if mip_model.model.SolCount > 0:
    status_mip = "OPTIMAL" if mip_model.model.status == GRB.OPTIMAL else "FEASIBLE"
    obj_mip = mip_model.model.ObjVal
else:
    status_mip = "INFEASIBLE / TIME_OUT"
    obj_mip = "N/A"

print(f"  - Parse Time  : {t1 - t0:.4f} s")
print(f"  - Build Time  : {mip_build_time:.4f} s")
print(f"  - Solve Time  : {mip_solve_time:.4f} s")
print(f"  - Total Time  : {(t1-t0) + mip_build_time + mip_solve_time:.4f} s")
print(f"  - Status      : {status_mip} (Obj: {obj_mip})")
print("-" * 60)

# --------------------------
# 2. OR-Tools CP-SAT Model
# --------------------------
print(">>> [OR-Tools CP-SAT Model]")
t0 = time.time()
cp_instance = CPInstance.from_json(problem_file)
t1 = time.time()

t2 = time.time()
cp_model = DisplibCPModel(cp_instance)
cp_model.solver.parameters.log_search_progress = False
cp_build_time = time.time() - t2

t3 = time.time()
status_cp = cp_model.optimize(time_limit=TIME_LIMIT)
cp_solve_time = time.time() - t3

obj_cp = cp_model.obj_val if status_cp in ["OPTIMAL", "FEASIBLE"] else "N/A"

print(f"  - Parse Time  : {t1 - t0:.4f} s")
print(f"  - Build Time  : {cp_build_time:.4f} s")
print(f"  - Solve Time  : {cp_solve_time:.4f} s")
print(f"  - Total Time  : {(t1-t0) + cp_build_time + cp_solve_time:.4f} s")
print(f"  - Status      : {status_cp} (Obj: {obj_cp})")
print("=" * 60)
