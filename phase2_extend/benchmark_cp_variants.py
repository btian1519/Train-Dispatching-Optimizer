import argparse
import glob
import json
import os
import time
import traceback
from datetime import datetime

from rolling_horizon_overlap import solve_overlapping_rolling_horizon
from run_greedy_baseline import solve_greedy
from src.cp_model import DisplibCPModel
from src.data_parser import DisplibInstance


METHOD_STANDARD = "standard_cp_sat"
METHOD_OVERLAP = "rolling_window"
METHOD_GREEDY = "greedy"
METHODS = (METHOD_STANDARD, METHOD_OVERLAP, METHOD_GREEDY)


def round_objective(value):
    return None if value is None else int(round(value))


def safe_remove(path):
    if path and os.path.exists(path):
        os.remove(path)


def collect_instance_features(file_path):
    instance = DisplibInstance.from_json(file_path)
    return {
        "num_trains": len(instance.trains),
        "num_operations": sum(len(train.operations) for train in instance.trains),
        "num_conflicts": len(instance.find_conflict_pairs()),
    }


def standard_result_template(method, elapsed, output_file):
    return {
        "method": method,
        "status": "ERROR",
        "feasible": False,
        "optimal_proven": False,
        "objective_value": None,
        "wall_clock_time": elapsed,
        "output_file": output_file,
        "error": None,
    }


def run_standard_cp_sat(file_path, output_file, time_limit, num_workers):
    safe_remove(output_file)
    start_time = time.time()
    result = standard_result_template(METHOD_STANDARD, 0.0, output_file)

    try:
        instance = DisplibInstance.from_json(file_path)
        model = DisplibCPModel(instance)
        model.solver.parameters.log_search_progress = False

        remaining_time = max(0.001, float(time_limit) - (time.time() - start_time))
        if remaining_time <= 0.001:
            result.update({
                "status": "TIME_LIMIT",
                "wall_clock_time": time.time() - start_time,
                "feasible": False,
                "optimal_proven": False,
                "objective_value": None,
            })
            safe_remove(output_file)
            return result

        status = model.optimize(time_limit=remaining_time, num_workers=num_workers)
        elapsed = time.time() - start_time

        result.update({
            "status": status,
            "wall_clock_time": elapsed,
            "feasible": status in {"OPTIMAL", "FEASIBLE"},
            "optimal_proven": status == "OPTIMAL",
            "objective_value": round_objective(model.obj_val) if status in {"OPTIMAL", "FEASIBLE"} else None,
        })

        if elapsed >= time_limit and status == "FEASIBLE":
            result["status"] = "TIME_LIMIT"
            result["optimal_proven"] = False

        if result["feasible"]:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            model.export_solution(output_file)
        else:
            safe_remove(output_file)

    except Exception as exc:
        result["wall_clock_time"] = time.time() - start_time
        result["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
        safe_remove(output_file)

    return result


def run_overlap_cp(file_path, output_file, time_limit, window_size, step_size, batch_time_limit):
    safe_remove(output_file)
    start_time = time.time()
    result = standard_result_template(METHOD_OVERLAP, 0.0, output_file)

    try:
        solver_result = solve_overlapping_rolling_horizon(
            dataset_path=file_path,
            output_path=output_file,
            window_size=window_size,
            step_size=step_size,
            time_limit_per_batch=batch_time_limit,
            global_time_limit=time_limit,
        )
        elapsed = time.time() - start_time

        result.update({
            "status": (solver_result or {}).get("status", "ERROR"),
            "wall_clock_time": elapsed,
            "feasible": bool((solver_result or {}).get("feasible")) and os.path.exists(output_file),
            "optimal_proven": False,
            "objective_value": (solver_result or {}).get("objective_value"),
        })

        if not result["feasible"]:
            result["objective_value"] = None
            safe_remove(output_file)

    except Exception as exc:
        result["wall_clock_time"] = time.time() - start_time
        result["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
        safe_remove(output_file)

    return result


def run_greedy_cp(file_path, output_file, time_limit, per_train_time_limit):
    safe_remove(output_file)
    start_time = time.time()
    result = standard_result_template(METHOD_GREEDY, 0.0, output_file)

    try:
        solver_result = solve_greedy(
            file_path,
            output_file,
            time_limit_per_train=per_train_time_limit,
            global_time_limit=time_limit,
        )
        elapsed = time.time() - start_time

        result.update({
            "status": (solver_result or {}).get("status", "ERROR"),
            "wall_clock_time": elapsed,
            "feasible": bool((solver_result or {}).get("status") in {"OPTIMAL", "FEASIBLE"}) and os.path.exists(output_file),
            "optimal_proven": False,
            "objective_value": (solver_result or {}).get("objective_value"),
        })

        if not result["feasible"]:
            result["objective_value"] = None
            safe_remove(output_file)

    except Exception as exc:
        result["wall_clock_time"] = time.time() - start_time
        result["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
        safe_remove(output_file)

    return result


def summarize(all_instances):
    summary = {}
    for method in METHODS:
        method_runs = [entry["methods"][method] for entry in all_instances]
        feasible_runs = [run for run in method_runs if run["feasible"]]
        best_known_runs = [run for run in method_runs if run.get("matched_best_known")]
        summary[method] = {
            "instance_count": len(method_runs),
            "feasible_count": len(feasible_runs),
            "best_known_count": len(best_known_runs),
            "optimal_proven_count": sum(1 for run in method_runs if run.get("optimal_proven")),
            "avg_wall_clock_time": round(sum(run["wall_clock_time"] for run in method_runs) / len(method_runs), 4) if method_runs else None,
        }
    return summary


def build_payload(args, dataset_dir, all_instances):
    return {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "dataset_dir": dataset_dir,
            "pattern": args.pattern,
            "time_limit": args.time_limit,
            "num_workers": args.num_workers,
            "overlap_window": args.overlap_window,
            "overlap_step": args.overlap_step,
            "overlap_batch_time": args.overlap_batch_time,
            "greedy_per_train_time": args.greedy_per_train_time,
            "methods": list(METHODS),
            "completed_instances": len(all_instances),
        },
        "instances": all_instances,
        "summary": summarize(all_instances),
    }


def save_payload(results_file, payload):
    os.makedirs(os.path.dirname(results_file), exist_ok=True)
    with open(results_file, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Benchmark CP-SAT variants on DISPLIB instances.")
    parser.add_argument("--dataset-dir", type=str, default=os.path.join("..", "dataset", "displib_problems"))
    parser.add_argument("--pattern", type=str, default="*.json")
    parser.add_argument("--time-limit", type=float, default=60.0, help="Global wall-clock time limit per instance and method.")
    parser.add_argument("--num-workers", type=int, default=8)
    parser.add_argument("--overlap-window", type=int, default=10)
    parser.add_argument("--overlap-step", type=int, default=5)
    parser.add_argument("--overlap-batch-time", type=float, default=30.0)
    parser.add_argument("--greedy-per-train-time", type=float, default=5.0)
    parser.add_argument("--max-instances", type=int, default=None)
    parser.add_argument("--results-file", type=str, default=os.path.join("output", "benchmark_cp_variants", "benchmark_results_cp_variants.json"))
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    dataset_dir = os.path.abspath(args.dataset_dir)
    file_paths = sorted(glob.glob(os.path.join(dataset_dir, args.pattern)))
    if args.max_instances is not None:
        file_paths = file_paths[:args.max_instances]

    if not file_paths:
        raise FileNotFoundError(f"No instances found in {dataset_dir} matching {args.pattern}")

    instances = []
    for file_path in file_paths:
        features = collect_instance_features(file_path)
        instances.append({
            "instance_name": os.path.splitext(os.path.basename(file_path))[0],
            "file_path": file_path,
            **features,
        })

    instances.sort(key=lambda item: (item["num_trains"], item["num_conflicts"], item["instance_name"]))

    results_root = os.path.join(script_dir, "output", "benchmark_cp_variants")
    os.makedirs(results_root, exist_ok=True)

    benchmark_rows = []
    results_file = os.path.abspath(args.results_file)
    for index, instance_info in enumerate(instances, start=1):
        instance_name = instance_info["instance_name"]
        file_path = instance_info["file_path"]

        print("\n" + "=" * 72)
        print(f"[{index}/{len(instances)}] Benchmarking {instance_name}")
        print(f"    trains={instance_info['num_trains']}  conflicts={instance_info['num_conflicts']}")
        print("=" * 72)

        method_outputs = {
            METHOD_STANDARD: os.path.join(results_root, METHOD_STANDARD, f"solution_{instance_name}.json"),
            METHOD_OVERLAP: os.path.join(results_root, METHOD_OVERLAP, f"solution_{instance_name}.json"),
            METHOD_GREEDY: os.path.join(results_root, METHOD_GREEDY, f"solution_{instance_name}.json"),
        }

        standard = run_standard_cp_sat(
            file_path=file_path,
            output_file=method_outputs[METHOD_STANDARD],
            time_limit=args.time_limit,
            num_workers=args.num_workers,
        )
        print(f"  [{METHOD_STANDARD}] status={standard['status']} time={standard['wall_clock_time']:.2f}s obj={standard['objective_value']}")

        overlap = run_overlap_cp(
            file_path=file_path,
            output_file=method_outputs[METHOD_OVERLAP],
            time_limit=args.time_limit,
            window_size=args.overlap_window,
            step_size=args.overlap_step,
            batch_time_limit=args.overlap_batch_time,
        )
        print(f"  [{METHOD_OVERLAP}] status={overlap['status']} time={overlap['wall_clock_time']:.2f}s obj={overlap['objective_value']}")

        greedy = run_greedy_cp(
            file_path=file_path,
            output_file=method_outputs[METHOD_GREEDY],
            time_limit=args.time_limit,
            per_train_time_limit=args.greedy_per_train_time,
        )
        print(f"  [{METHOD_GREEDY}] status={greedy['status']} time={greedy['wall_clock_time']:.2f}s obj={greedy['objective_value']}")

        method_results = {
            METHOD_STANDARD: standard,
            METHOD_OVERLAP: overlap,
            METHOD_GREEDY: greedy,
        }

        feasible_objectives = [
            result["objective_value"]
            for result in method_results.values()
            if result["feasible"] and result["objective_value"] is not None
        ]
        best_known_objective = min(feasible_objectives) if feasible_objectives else None

        for result in method_results.values():
            result["matched_best_known"] = (
                result["feasible"]
                and best_known_objective is not None
                and result["objective_value"] == best_known_objective
            )

        benchmark_rows.append({
            **instance_info,
            "best_known_objective": best_known_objective,
            "methods": method_results,
        })

        payload = build_payload(args, dataset_dir, benchmark_rows)
        save_payload(results_file, payload)
        print(f"  [checkpoint] saved partial results after {index}/{len(instances)} instances")

    payload = build_payload(args, dataset_dir, benchmark_rows)
    save_payload(results_file, payload)

    print("\nSaved benchmark results to:")
    print(results_file)


if __name__ == "__main__":
    main()