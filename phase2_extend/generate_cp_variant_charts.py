import argparse
import json
import os
from collections import defaultdict

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    matplotlib = None
    plt = None


METHOD_LABELS = {
    "standard_cp_sat": "CP-SAT",
    "rolling_window": "CP-SAT + Rolling Window",
    "greedy": "CP-SAT + Greedy",
}

METHOD_COLORS = {
    "standard_cp_sat": "#0B6E4F",
    "rolling_window": "#2F80ED",
    "greedy": "#D35400",
}


def load_results(results_file):
    with open(results_file, "r", encoding="utf-8") as handle:
        return json.load(handle)


def grouped_metric_points(instances, method, x_key):
    grouped = defaultdict(list)
    raw_points = []

    for instance in instances:
        run = instance["methods"][method]
        x_val = instance[x_key]
        y_val = run["wall_clock_time"]
        raw_points.append((x_val, y_val, run["feasible"]))
        grouped[x_val].append(y_val)

    grouped_points = []
    for x_val in sorted(grouped):
        values = sorted(grouped[x_val])
        median = values[len(values) // 2] if len(values) % 2 == 1 else (values[len(values) // 2 - 1] + values[len(values) // 2]) / 2
        grouped_points.append((x_val, median))

    return grouped_points, raw_points


def plot_time_vs_metric(instances, methods, x_key, x_label, output_file, time_limit):
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    fig.patch.set_facecolor("#F7F6F2")
    ax.set_facecolor("#F7F6F2")

    for method in methods:
        grouped_points, raw_points = grouped_metric_points(instances, method, x_key)
        xs = [item[0] for item in grouped_points]
        ys = [item[1] for item in grouped_points]

        ax.plot(xs, ys, marker="o", linewidth=2.2, markersize=6, color=METHOD_COLORS[method], label=METHOD_LABELS[method], zorder=3)

        feasible_x = [x for x, y, feasible in raw_points if feasible]
        feasible_y = [y for x, y, feasible in raw_points if feasible]
        failed_x = [x for x, y, feasible in raw_points if not feasible]
        failed_y = [y for x, y, feasible in raw_points if not feasible]

        ax.scatter(feasible_x, feasible_y, color=METHOD_COLORS[method], alpha=0.18, s=28, zorder=2)
        if failed_x:
            ax.scatter(failed_x, failed_y, color=METHOD_COLORS[method], marker="x", alpha=0.7, s=40, zorder=4)

    ax.axhline(time_limit, linestyle="--", linewidth=1.2, color="#7F8C8D", alpha=0.8, label=f"Time limit = {time_limit:.0f}s")
    ax.set_xlabel(x_label)
    ax.set_ylabel("Wall-clock total time (s)")
    ax.set_title(f"Wall-clock Time vs {x_label}")
    ax.grid(True, linestyle="--", linewidth=0.6, alpha=0.4)
    ax.legend(framealpha=0.92)
    fig.tight_layout()
    fig.savefig(output_file, bbox_inches="tight")
    plt.close(fig)


def cactus_series(instances, method, selector_key):
    selected_times = [
        instance["methods"][method]["wall_clock_time"]
        for instance in instances
        if instance["methods"][method].get(selector_key)
    ]
    selected_times.sort()
    x_vals = list(range(1, len(selected_times) + 1))
    return x_vals, selected_times


def plot_cactus(instances, methods, selector_key, title, output_file):
    fig, ax = plt.subplots(figsize=(10.0, 5.8))
    fig.patch.set_facecolor("#F7F6F2")
    ax.set_facecolor("#F7F6F2")

    for method in methods:
        x_vals, y_vals = cactus_series(instances, method, selector_key)
        if not x_vals:
            continue
        ax.step(x_vals, y_vals, where="post", linewidth=2.4, color=METHOD_COLORS[method], label=METHOD_LABELS[method])
        ax.scatter(x_vals, y_vals, color=METHOD_COLORS[method], s=20, alpha=0.75)

    ax.set_xlabel("Number of instances solved")
    ax.set_ylabel("Wall-clock total time (s)")
    ax.set_title(title)
    ax.grid(True, linestyle="--", linewidth=0.6, alpha=0.4)
    ax.legend(framealpha=0.92)
    fig.tight_layout()
    fig.savefig(output_file, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Generate charts for CP variant benchmark results.")
    parser.add_argument("--results-file", type=str, default=os.path.join("output", "benchmark_cp_variants", "benchmark_results_cp_variants.json"))
    parser.add_argument("--output-dir", type=str, default=os.path.join("output", "benchmark_cp_variants", "charts"))
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    results_path = os.path.abspath(args.results_file)
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    payload = load_results(results_path)
    instances = payload["instances"]
    methods = payload["metadata"]["methods"]
    time_limit = payload["metadata"]["time_limit"]

    if plt is None:
        raise ModuleNotFoundError("matplotlib is required to generate charts. Install it in the active Python environment first.")

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 150,
    })

    plot_time_vs_metric(
        instances=instances,
        methods=methods,
        x_key="num_trains",
        x_label="Number of trains",
        output_file=os.path.join(output_dir, "time_vs_num_trains.png"),
        time_limit=time_limit,
    )

    plot_time_vs_metric(
        instances=instances,
        methods=methods,
        x_key="num_conflicts",
        x_label="Number of conflict pairs",
        output_file=os.path.join(output_dir, "time_vs_num_conflicts.png"),
        time_limit=time_limit,
    )

    for instance in instances:
        for method in methods:
            instance["methods"][method]["feasible_cactus"] = instance["methods"][method]["feasible"]
            instance["methods"][method]["best_known_cactus"] = instance["methods"][method].get("matched_best_known", False)

    plot_cactus(
        instances=instances,
        methods=methods,
        selector_key="feasible_cactus",
        title="Feasible Cactus Plot",
        output_file=os.path.join(output_dir, "cactus_feasible.png"),
    )

    plot_cactus(
        instances=instances,
        methods=methods,
        selector_key="best_known_cactus",
        title="Best-known Objective Cactus Plot",
        output_file=os.path.join(output_dir, "cactus_best_known.png"),
    )

    print("Saved charts to:")
    print(output_dir)


if __name__ == "__main__":
    main()