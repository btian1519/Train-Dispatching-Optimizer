import os
import sys
import json
import time
from collections import defaultdict
from src.data_parser import DisplibInstance
from src.cp_model import DisplibCPModel

def solve_rolling_horizon(dataset_path: str, output_path: str, batch_size: int = 10, time_limit_per_batch: int = 30):
    print(f"==================================================")
    print(f"[*] ROLLING HORIZON SOLVER INITIATED")
    print(f"Dataset: {os.path.basename(dataset_path)}")
    print(f"Batch Size: {batch_size} trains per chunk")
    print(f"Time Limit: {time_limit_per_batch}s per chunk")
    print(f"==================================================\n")
    
    start_time = time.time()
    
    # 1. Load full instance
    print("[1] Loading full dataset...")
    full_instance = DisplibInstance.from_json(dataset_path)
    total_trains = len(full_instance.trains)
    print(f"    Total Trains: {total_trains}")
    
    # Sort trains logically (by ID, assuming ID correlates with importance or initial dispatch order)
    # Note: Sorting by start_lb of their entry operations is even better for real-world RHH.
    sorted_trains = sorted(full_instance.trains, key=lambda t: t.id)
    
    blocked_resources = defaultdict(list)
    all_events = []
    total_objective = 0
    
    # 2. Slice and Solve iteratively
    print("\n[2] Commencing Rolling Horizon Batches...")
    
    for i in range(0, total_trains, batch_size):
        batch = sorted_trains[i:i+batch_size]
        batch_ids = [t.id for t in batch]
        print(f"\n---> Batch {i//batch_size + 1} | Trains: {batch_ids[0]} to {batch_ids[-1]} ({len(batch)} trains)")
        
        # Create mini instance
        # We pass the full objective list; the CP model natively ignores objectives for missing trains
        mini_instance = DisplibInstance(trains=batch, objective=full_instance.objective)
        
        # Instantiate CP-SAT with blocked resources
        # We MUST merge overlapping/touching intervals and pad the final end time by +1 ms.
        # This prevents 'simultaneous resource swapping' deadlocks in displib_verify.py 
        # without causing internal overlap infeasibility in CP-SAT's AddNoOverlap.
        merged_blocked_resources = defaultdict(list)
        for res, intervals in blocked_resources.items():
            if not intervals: continue
            intervals.sort(key=lambda x: x[0])
            merged = []
            c_st, c_en = intervals[0]
            for st, en in intervals[1:]:
                if st <= c_en:
                    c_en = max(c_en, en)
                else:
                    merged.append((c_st, c_en + 1))
                    c_st, c_en = st, en
            merged.append((c_st, c_en + 1))
            merged_blocked_resources[res] = merged
            
        print(f"    Building CP-SAT model with {sum(len(v) for v in merged_blocked_resources.values())} merged resource blackholes...")
        cp_model = DisplibCPModel(mini_instance, blocked_resources=merged_blocked_resources)
        
        # Solve
        status = cp_model.optimize(time_limit=time_limit_per_batch)
        print(f"    Status: {status} | Sub-Objective: {cp_model.obj_val}")
        
        if status not in ["OPTIMAL", "FEASIBLE"]:
            print(f"    [!] ERROR: Failed to find a feasible solution for this batch!")
            print(f"    This can happen in greedy heuristics if previous blackholes completely block the route.")
            return
            
        total_objective += cp_model.obj_val
        
        # Extract events and generate NEW blackholes
        for train in batch:
            t_id = train.id
            for op in train.operations:
                o_id = op.id
                
                # If this operation was selected by the solver
                if cp_model.solver.BooleanValue(cp_model.x[t_id, o_id]):
                    st = cp_model.solver.Value(cp_model.starts[t_id, o_id])
                    en = cp_model.solver.Value(cp_model.ends[t_id, o_id])
                    
                    # 1. Save the event for final JSON
                    # Offset u_rank by batch index (i) to ensure older batches always 'release' before newer batches 'allocate' at the same millisecond!
                    global_u_rank = i * 1000000 + cp_model.solver.Value(cp_model.u[t_id, o_id])
                    
                    all_events.append({
                        "operation": o_id,
                        "time": int(st),
                        "train": t_id,
                        "_u_rank": global_u_rank
                    })
                    
                    # 2. Create Resource Blackholes for future batches!
                    for r_data in op.resources:
                        res_name = r_data.resource
                        rel_time = int(r_data.release_time)
                        # The resource is blocked from `st` to `en + rel_time`
                        blocked_resources[res_name].append((st, en + rel_time))
                        
    print("\n[3] All batches completed successfully!")
    
    # 3. Final Aggregation and Topological Sorting
    # To pass displib_verify.py, events at the exact same millisecond must be sorted such that
    # 'Releases' happen before 'Allocations' for shared resources.
    all_events.sort(key=lambda x: (x["time"], x["train"])) # Base sort
    
    # Pre-calculate previous operations for each train to know what resources are being released
    train_events = defaultdict(list)
    for e in all_events:
        train_events[e["train"]].append(e)
        
    for t_id, ev_list in train_events.items():
        for i, e in enumerate(ev_list):
            e["_prev_op"] = ev_list[i-1]["operation"] if i > 0 else None

    def get_resources(t_id, o_id):
        if o_id is None: return set()
        return {r.resource for r in full_instance.trains[t_id].get_operation(o_id).resources}

    # Group by time and sort topologically within each time slice
    time_groups = defaultdict(list)
    for e in all_events:
        time_groups[e["time"]].append(e)
        
    final_sorted_events = []
    
    for t in sorted(time_groups.keys()):
        group = time_groups[t]
        if len(group) <= 1:
            final_sorted_events.extend(group)
            continue
            
        # Build dependency graph for this time slice
        # Node: event index in `group`
        # Edge: A -> B means A must happen before B
        adj = {i: [] for i in range(len(group))}
        in_degree = {i: 0 for i in range(len(group))}
        
        for i, e1 in enumerate(group):
            for j, e2 in enumerate(group):
                if i == j: continue
                # 1. Same train physical sequence
                if e1["train"] == e2["train"] and e2["_prev_op"] == e1["operation"]:
                    adj[i].append(j)
                    in_degree[j] += 1
                
                # 2. Resource Release -> Allocate dependency (ONLY between different trains!)
                if e1["train"] != e2["train"]:
                    # displib_verify.py unconditionally frees ALL resources from the previous operation,
                    # and allocates ALL resources for the new operation.
                    res_released_by_e1 = get_resources(e1["train"], e1["_prev_op"])
                    res_allocated_by_e2 = get_resources(e2["train"], e2["operation"])
                    
                    if res_released_by_e1.intersection(res_allocated_by_e2):
                        adj[i].append(j)
                        in_degree[j] += 1

        # Kahn's algorithm for topological sort
        queue = [i for i in range(len(group)) if in_degree[i] == 0]
        topo_order = []
        
        while queue:
            # Sort queue to ensure determinism (e.g., by train id)
            queue.sort(key=lambda idx: group[idx]["train"])
            curr = queue.pop(0)
            topo_order.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    
        # If there's a cycle (should be mathematically impossible due to CP-SAT NoOverlap), just append remaining
        if len(topo_order) != len(group):
            remaining = set(range(len(group))) - set(topo_order)
            topo_order.extend(sorted(list(remaining), key=lambda idx: group[idx]["train"]))
            
        for idx in topo_order:
            final_sorted_events.append(group[idx])
            
    all_events = final_sorted_events
    
    # Clean up temporary keys
    for e in all_events:
        if "_u_rank" in e: del e["_u_rank"]
        if "_prev_op" in e: del e["_prev_op"]
        
    output = {
        "events": all_events,
        "objective_value": int(round(total_objective))
    }
    
    # 4. Export
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=4)
        
    elapsed = time.time() - start_time
    print(f"\n[*] SUCCESS! Entire Rolling Horizon completed in {elapsed:.2f}s")
    print(f"Greedy Objective Value: {int(round(total_objective))}")
    print(f"Exported to: {output_path}")
    print(f"==================================================")

if __name__ == "__main__":
    # Test on one of the massive full instances!
    import argparse
    parser = argparse.ArgumentParser(description="Rolling Horizon Heuristic for Train Dispatching")
    parser.add_argument("--input", type=str, default="../dataset/displib_problems/nor1_full_0.json")
    parser.add_argument("--output", type=str, default="output/solution_rh_nor1_full_0.json")
    parser.add_argument("--batch", type=int, default=10, help="Number of trains per rolling horizon batch")
    parser.add_argument("--time", type=int, default=30, help="Time limit per batch in seconds")
    
    args = parser.parse_args()
    
    # Ensure correct CWD
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.getcwd() != script_dir:
        os.chdir(script_dir)
        
    solve_rolling_horizon(args.input, args.output, args.batch, args.time)
