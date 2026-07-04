"""
=============================================================================
rolling_horizon_overlap.py  —  Phase 2: Overlapping Rolling Horizon (Look-ahead)
=============================================================================
This script extends the basic Rolling Horizon Heuristic (rolling_horizon.py)
with an **Overlapping Window** strategy, also known as a "Look-ahead" heuristic.

Key Difference from rolling_horizon.py (Disjoint / Greedy):
  - DISJOINT  (old): Window [0..9] is solved and ALL trains 0-9 are locked.
                     Window [10..19] is solved next. No revisiting.
  - OVERLAPPING (new): Window [0..9] is solved, but ONLY trains 0-4 are locked.
                     Window [5..14] is solved next — trains 5-9 get a second
                     chance to re-optimize given the context of trains 10-14.
                     This "look-ahead" improves global objective quality.

Parameters:
  --batch   (window_size) : Total trains per solving window. Default: 10
  --step    (step_size)   : How many trains to commit & lock after each batch.
                            Must be < batch. Default: 5 (= batch/2)
                            The look-ahead horizon = batch - step trains.
  --time                  : CP-SAT time limit per batch in seconds. Default: 30

Usage:
  python rolling_horizon_overlap.py --input <path_to_problem.json>
                                    --output <path_to_solution.json>
                                    --batch 10 --step 5 --time 30
=============================================================================
"""

import os
import sys
import json
import time
from collections import defaultdict
from src.data_parser import DisplibInstance
from src.cp_model import DisplibCPModel


def _merge_and_pad_blackholes(blocked_resources: dict) -> dict:
    """
    Merges overlapping/touching blocked intervals for each resource and pads
    the end of each merged block by +1 ms.

    This is critical to prevent 'simultaneous resource swapping' deadlocks in
    displib_verify.py without causing internal CP-SAT NoOverlap infeasibility.

    Args:
        blocked_resources: dict mapping resource name -> list of (start, end) tuples

    Returns:
        A new dict with merged and padded intervals.
    """
    merged = defaultdict(list)
    for res, intervals in blocked_resources.items():
        if not intervals:
            continue
        intervals.sort(key=lambda x: x[0])
        c_st, c_en = intervals[0]
        merged_list = []
        for st, en in intervals[1:]:
            if st <= c_en:
                c_en = max(c_en, en)
            else:
                merged_list.append((c_st, c_en + 1))
                c_st, c_en = st, en
        merged_list.append((c_st, c_en + 1))
        merged[res] = merged_list
    return merged


def solve_overlapping_rolling_horizon(
    dataset_path: str,
    output_path: str,
    window_size: int = 10,
    step_size: int = 5,
    time_limit_per_batch: int = 30,
    global_time_limit: float = None
):
    """
    Solves the train dispatching problem using the Overlapping Rolling Horizon
    (Look-ahead) heuristic.

    Args:
        dataset_path:        Path to the DISPLIB problem JSON file.
        output_path:         Path to write the solution JSON file.
        window_size:         Number of trains in each solving window.
        step_size:           Number of trains to commit (lock) after each window.
                             The look-ahead = window_size - step_size trains.
        time_limit_per_batch: CP-SAT time limit per window in seconds.
    """
    if step_size >= window_size:
        raise ValueError(
            f"step_size ({step_size}) must be strictly less than window_size ({window_size}). "
            "The look-ahead overlap = window_size - step_size must be >= 1."
        )

    look_ahead = window_size - step_size

    print("=" * 60)
    print("[*] OVERLAPPING ROLLING HORIZON SOLVER (LOOK-AHEAD)")
    print(f"    Dataset     : {os.path.basename(dataset_path)}")
    print(f"    Window Size : {window_size} trains  (trains solved together)")
    print(f"    Step Size   : {step_size} trains   (trains committed per step)")
    print(f"    Look-ahead  : {look_ahead} trains   (trains re-optimized each step)")
    print(f"    Time Limit  : {time_limit_per_batch}s per window")
    print("=" * 60 + "\n")

    start_time = time.time()

    # -------------------------------------------------------------------------
    # Step 1: Load Dataset
    # -------------------------------------------------------------------------
    print("[1] Loading full dataset...")
    full_instance = DisplibInstance.from_json(dataset_path)
    total_trains = len(full_instance.trains)
    print(f"    Total Trains : {total_trains}")

    # Sort trains by ID (consistent with the original rolling_horizon.py)
    sorted_trains = sorted(full_instance.trains, key=lambda t: t.id)

    # -------------------------------------------------------------------------
    # Data Structures
    # -------------------------------------------------------------------------
    # blocked_resources: accumulated hard constraints from COMMITTED trains.
    # Only trains that have been "locked" contribute to this.
    blocked_resources = defaultdict(list)

    # Precompute objective info per train: maps train_id -> (obj_op_id, threshold_ms, coeff)
    # Used to accurately compute committed objective rather than using the full batch sum.
    train_obj_info = {}  # train_id -> (operation_id, threshold_ms, coeff)
    for obj_entry in full_instance.objective:
        # ObjectiveComponent fields: comp_type, train, operation, threshold (ms), coeff
        train_obj_info[obj_entry.train] = (
            obj_entry.operation,
            int(obj_entry.threshold),   # already in ms
            float(obj_entry.coeff)
        )

    # committed_results: maps train_id -> list of event dicts for committed trains.
    # This is the final result we will export.
    committed_results = {}

    # total_objective: sum of objectives from each committed batch.
    total_objective = 0

    # -------------------------------------------------------------------------
    # Step 2: Overlapping Window Loop
    # -------------------------------------------------------------------------
    print("\n[2] Commencing Overlapping Rolling Horizon Batches...")

    batch_num = 0
    cursor = 0  # index of the first UNCOMMITTED train

    while cursor < total_trains:
        elapsed = time.time() - start_time
        if global_time_limit is not None and elapsed >= global_time_limit:
            print("\n    [!] Global time limit reached before all windows were committed.")
            if os.path.exists(output_path):
                os.remove(output_path)
            return {
                "status": "TIME_LIMIT",
                "objective_value": None,
                "elapsed": elapsed,
                "feasible": False,
            }

        batch_num += 1

        # Slice the window: [cursor, cursor + window_size)
        window_end = min(cursor + window_size, total_trains)
        window_trains = sorted_trains[cursor:window_end]

        # The trains we will COMMIT (lock) after this solve:
        #   - If this is not the last window, commit only the first `step_size` trains.
        #   - If this is the last window, commit all remaining trains.
        is_last_window = (window_end == total_trains)
        commit_count = len(window_trains) if is_last_window else step_size

        commit_train_ids = set(t.id for t in window_trains[:commit_count])
        lookahead_train_ids = set(t.id for t in window_trains[commit_count:])

        print(f"\n---> Batch {batch_num} | Window: Train {window_trains[0].id} to {window_trains[-1].id}"
              f" ({len(window_trains)} trains total)")
        print(f"     Commit : {commit_count} trains  "
              f"(IDs {window_trains[0].id}-{window_trains[commit_count-1].id})")
        if not is_last_window:
            print(f"     Look-ahead : {len(window_trains) - commit_count} trains  "
                  f"(IDs {window_trains[commit_count].id}-{window_trains[-1].id}  <- re-solved next step)")

        # Build mini-instance for this window
        mini_instance = DisplibInstance(trains=window_trains, objective=full_instance.objective)

        # Merge and pad blackholes from previously committed trains
        merged_bh = _merge_and_pad_blackholes(blocked_resources)
        print(f"     Blackholes : {sum(len(v) for v in merged_bh.values())} merged resource blocks")

        # Solve with CP-SAT
        cp_model = DisplibCPModel(mini_instance, blocked_resources=merged_bh)
        remaining_global = None
        if global_time_limit is not None:
            remaining_global = max(0.001, global_time_limit - (time.time() - start_time))
        local_time_limit = time_limit_per_batch if remaining_global is None else min(time_limit_per_batch, remaining_global)
        status = cp_model.optimize(time_limit=local_time_limit)
        print(f"     Status : {status} | Sub-Objective: {cp_model.obj_val}")

        if status not in ["OPTIMAL", "FEASIBLE"]:
            print(f"\n    [!] ERROR: INFEASIBLE in Batch {batch_num}! Cannot commit any trains.")
            print(f"    Hint: Try increasing --time or decreasing --step (more overlap).")
            elapsed = time.time() - start_time
            if os.path.exists(output_path):
                os.remove(output_path)
            return {
                "status": status,
                "objective_value": None,
                "elapsed": elapsed,
                "feasible": False,
            }

        # -----------------------------------------------------------------
        # Extract results: only COMMIT the first `step_size` trains.
        # The look-ahead trains are intentionally left uncommitted; they will
        # be re-solved in the NEXT window with better global context.
        # -----------------------------------------------------------------
        batch_obj_committed = 0.0

        for train in window_trains:
            t_id = train.id

            if t_id not in commit_train_ids:
                # This is a look-ahead train. We got a solution for it, but
                # we DISCARD it — it will be re-optimized in the next batch.
                continue

            train_events = []
            for op in train.operations:
                o_id = op.id
                if cp_model.solver.BooleanValue(cp_model.x[t_id, o_id]):
                    st = cp_model.solver.Value(cp_model.starts[t_id, o_id])
                    en = cp_model.solver.Value(cp_model.ends[t_id, o_id])

                    # Global u-rank: ensures intra-batch ordering is preserved
                    # even across multiple batch outputs during final sort.
                    global_u_rank = cursor * 1_000_000 + cp_model.solver.Value(cp_model.u[t_id, o_id])

                    train_events.append({
                        "operation": o_id,
                        "time": int(st),
                        "train": t_id,
                        "_u_rank": global_u_rank
                    })

                    # Generate resource blackholes for future batches
                    for r_data in op.resources:
                        res_name = r_data.resource
                        rel_time = int(r_data.release_time)
                        blocked_resources[res_name].append((st, en + rel_time))

            committed_results[t_id] = train_events

        # Add only the objective contribution of the COMMITTED trains.
        # look-ahead trains are intentionally excluded — they will be re-solved next round.
        for t_id in commit_train_ids:
            if t_id not in train_obj_info:
                continue
            obj_op_id, threshold_ms, coeff = train_obj_info[t_id]
            # Find the committed event for the objective operation of this train
            if t_id in committed_results:
                for ev in committed_results[t_id]:
                    if ev["operation"] == obj_op_id:
                        arrival_ms = ev["time"]
                        penalty = max(0.0, (arrival_ms - threshold_ms) * coeff)
                        total_objective += penalty
                        break

        # Advance the cursor by step_size (commit_count)
        cursor += commit_count

    print("\n[3] All batches completed. Aggregating final event list...")

    # -------------------------------------------------------------------------
    # Step 3: Collect all committed events and sort them (topological sort)
    # -------------------------------------------------------------------------
    all_events = []
    for t_id in sorted(committed_results.keys()):
        all_events.extend(committed_results[t_id])

    # Base sort by time, then train id
    all_events.sort(key=lambda x: (x["time"], x["train"]))

    # Annotate each event with its predecessor operation (needed for topo sort)
    train_event_map = defaultdict(list)
    for e in all_events:
        train_event_map[e["train"]].append(e)

    for t_id, ev_list in train_event_map.items():
        for i, e in enumerate(ev_list):
            e["_prev_op"] = ev_list[i - 1]["operation"] if i > 0 else None

    def get_resources(t_id, o_id):
        if o_id is None:
            return set()
        return {r.resource for r in full_instance.trains[t_id].get_operation(o_id).resources}

    # Topological sort within each time slice (same as original rolling_horizon.py)
    time_groups = defaultdict(list)
    for e in all_events:
        time_groups[e["time"]].append(e)

    final_sorted_events = []

    for t in sorted(time_groups.keys()):
        group = time_groups[t]
        if len(group) <= 1:
            final_sorted_events.extend(group)
            continue

        adj = {i: [] for i in range(len(group))}
        in_degree = {i: 0 for i in range(len(group))}

        for i, e1 in enumerate(group):
            for j, e2 in enumerate(group):
                if i == j:
                    continue
                # Rule 1: Same-train physical sequence
                if e1["train"] == e2["train"] and e2["_prev_op"] == e1["operation"]:
                    adj[i].append(j)
                    in_degree[j] += 1

                # Rule 2: Resource release -> allocate (cross-train only)
                if e1["train"] != e2["train"]:
                    res_released = get_resources(e1["train"], e1["_prev_op"])
                    res_allocated = get_resources(e2["train"], e2["operation"])
                    if res_released.intersection(res_allocated):
                        adj[i].append(j)
                        in_degree[j] += 1

        # Kahn's algorithm (deterministic via train-id tie-breaking)
        queue = [i for i in range(len(group)) if in_degree[i] == 0]
        topo_order = []

        while queue:
            queue.sort(key=lambda idx: group[idx]["train"])
            curr = queue.pop(0)
            topo_order.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Fallback for rare cycles
        if len(topo_order) != len(group):
            remaining = set(range(len(group))) - set(topo_order)
            topo_order.extend(sorted(remaining, key=lambda idx: group[idx]["train"]))

        for idx in topo_order:
            final_sorted_events.append(group[idx])

    # -------------------------------------------------------------------------
    # Step 4: Recalculate true objective from the final solution
    # -------------------------------------------------------------------------
    # The total_objective accumulated from batch sums can be slightly inflated
    # due to look-ahead trains' objectives being double-counted. We do a final
    # pass over the committed events to compute the true objective.
    # For simplicity, re-use the solver's last accumulated value as a proxy.
    # (A precise recalculation would require replaying the objective function.)

    # Clean up internal keys
    for e in final_sorted_events:
        e.pop("_u_rank", None)
        e.pop("_prev_op", None)

    output_data = {
        "events": final_sorted_events,
        "objective_value": int(round(total_objective))
    }

    # -------------------------------------------------------------------------
    # Step 5: Export Solution
    # -------------------------------------------------------------------------
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=4)

    elapsed = time.time() - start_time
    print(f"\n[*] SUCCESS! Overlapping Rolling Horizon completed in {elapsed:.2f}s")
    print(f"    Greedy Objective Value : {int(round(total_objective))}")
    print(f"    Exported to            : {output_path}")
    print("=" * 60)
    return {
        "status": "FEASIBLE",
        "objective_value": int(round(total_objective)),
        "elapsed": elapsed,
        "feasible": True,
        "output_file": output_path,
    }


# =============================================================================
# Entry Point
# =============================================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Overlapping Rolling Horizon Heuristic (Look-ahead) for Train Dispatching",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default settings (window=10, step=5, look-ahead=5 trains)
  python rolling_horizon_overlap.py --input ../dataset/displib_problems/nor1_full_0.json

  # Aggressive look-ahead (commit only 3 trains per window of 10)
  python rolling_horizon_overlap.py --input ... --batch 10 --step 3 --time 60

  # Faster, smaller overlap
  python rolling_horizon_overlap.py --input ... --batch 10 --step 8 --time 30
        """
    )
    parser.add_argument("--input",  type=str, default="../dataset/displib_problems/nor1_full_0.json",
                        help="Path to the DISPLIB problem JSON file.")
    parser.add_argument("--output", type=str, default=None,
                        help="Path to the output solution JSON file. "
                             "Defaults to output/solution_rh_overlap_<basename>.")
    parser.add_argument("--batch",  type=int, default=10,
                        help="Window size: total trains per solving batch. (default: 10)")
    parser.add_argument("--step",   type=int, default=5,
                        help="Step size: trains committed per batch. "
                             "Look-ahead = batch - step. Must be < batch. (default: 5)")
    parser.add_argument("--time",   type=int, default=30,
                        help="CP-SAT time limit per batch in seconds. (default: 30)")

    args = parser.parse_args()

    # Ensure correct working directory (so src/ imports work)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.getcwd() != script_dir:
        os.chdir(script_dir)

    # Auto-generate output path if not specified
    if args.output is None:
        basename = os.path.splitext(os.path.basename(args.input))[0]
        args.output = f"output/solution_rh_overlap_{basename}.json"

    solve_overlapping_rolling_horizon(
        dataset_path=args.input,
        output_path=args.output,
        window_size=args.batch,
        step_size=args.step,
        time_limit_per_batch=args.time
    )
