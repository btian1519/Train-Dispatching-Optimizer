# Train Dispatching Optimization Lab

This repository contains the source code for the "Advanced Planning in Production and Logistics - Optimization Lab". It features two state-of-the-art mathematical models developed to solve the DISPLIB 2025 Train Dispatching Problem.

## Repository Structure

- **`phase1_baseline/`**: Contains the baseline Mixed-Integer Linear Programming (MIP) model implemented using **Gurobi**. 
  - `src/mip_model.py`: Core MIP mathematical formulation.
  - `main.py`: Entry script to test the model against basic testing instances.
  - `run_benchmark.py`: Script to batch-run tests and benchmark the solver.
  
- **`phase2_extend/`**: Contains the high-performance Constraint Programming (CP-SAT) model implemented using **Google OR-Tools**. This model elegantly handles cycle-crushing logic via topological sorting and `AddNoOverlap` interval variables.
  - `src/cp_model.py`: Core CP-SAT interval scheduling formulation.
  - `main_cp.py`: Entry script to test the CP-SAT model.
  - `run_benchmark_cp.py`: Batch benchmarking for the CP solver.
  
- **`dataset/`**: Contains all DISPLIB testing environments, maps, problems, and the official solution verification script (`displib_verify.py`).

- **`visualize_schedule.py`**: A powerful CLI/GUI script that reads the problem JSON and the output solution JSON to print out a highly readable, English-language timeline schedule. It also features a built-in reverse-engineering "Conflict Analysis" log that explains exactly which trains yielded to which trains at bottleneck resources.

## How to Run the Solvers

### 1. Running the CP-SAT Model (Recommended)
The Google OR-Tools CP-SAT model is highly scalable. You can run it on the testing instances by executing:
```bash
python phase2_extend/main_cp.py
```
This will automatically parse the testing `.json` files, run the optimizer, and save the schedule logs into the `phase2_extend/output/` directory.

### 2. Running the Gurobi MIP Model
Ensure you have an active Gurobi license. Run the baseline model via:
```bash
python phase1_baseline/main.py
```
Outputs are saved into `phase1_baseline/output/`.

## Analyzing and Verifying Solutions

### Visualization
To visualize a generated schedule (e.g., `nor1_critical_0`), you can simply run:
```bash
python visualize_schedule.py
```
A file picker will pop up. Select the problem JSON file first, and then the corresponding solution JSON file. The script will output a clean, readable schedule and a conflict resolution report.

### Verification
To strictly verify that a solution is feasible and does not violate any physics/collision rules according to the official DISPLIB schema, run the verifier:
```bash
python dataset/displib_verify/displib_verify.py <PATH_TO_PROBLEM.json> <PATH_TO_SOLUTION.json>
```
*Note: Our export logic handles simultaneous timeline events natively utilizing a Kahn's Algorithm topological sort to ensure the sequential verifier never encounters false positive cyclic deadlocks.*

## Contributing
Feel free to clone the repository and build upon the CP-SAT model for more complex railway networks!
