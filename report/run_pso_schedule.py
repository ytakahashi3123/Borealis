#!/usr/bin/env python3
"""PSO の重み係数の決め方 (inertia_schedule, coefficient_schedule) を比べる / Compare the weight schedules of PSO.

5 次元の Rastrigin 関数と球関数で、設定ごとに乱数の種を変えて NSEED 回ずつ走らせ、
それまでの最良の中央値などを report/data/pso_schedule_*.dat に書く。種は固定なので、毎回同じ結果になる。
ケースはその場で一時ディレクトリに作って消す（report/verification/ には置かない）。

使い方:  python3 report/run_pso_schedule.py [並列の数]      (既定 8。手元の 24 コアの機で約 40 秒)
"""
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "report", "data")

NUM_DIM = 5
NUM_PARTICLE = 20
NUM_STEP = 200
NSEED = 30
SEED0 = 1000
C_CLERC = 1.49618   # Clerc and Kennedy (2002) の縮約係数と等価な c1 = c2

# 設定: 名前 -> PSO のキー（書かないキーは既定の値）
SETTINGS = [
    ("constant_w0.5_c1.0",   dict(inertia=0.5, cognitive_coef=1.0, social_coef=1.0)),
    ("constant_w0.73_c1.5",  dict(inertia=0.7298, cognitive_coef=C_CLERC, social_coef=C_CLERC)),
    # 対照: c = 1.5 で w を 0.45, 0.5, 0.55, 0.6 と振ったうちで、Rastrigin の最良（2026-10-22）
    ("constant_w0.45_c1.5",  dict(inertia=0.45, cognitive_coef=C_CLERC, social_coef=C_CLERC)),
    ("linear_w_c1.5",        dict(inertia_schedule="linear", cognitive_coef=C_CLERC, social_coef=C_CLERC)),
    ("adaptive_w_c1.5",      dict(inertia_schedule="adaptive", cognitive_coef=C_CLERC, social_coef=C_CLERC)),
    ("linear_w_tvac",        dict(inertia_schedule="linear", coefficient_schedule="linear")),
    ("adaptive_w_tvac",      dict(inertia_schedule="adaptive", coefficient_schedule="linear")),
]
FUNCTIONS = {"rastrigin": 5.12, "sphere": 10.0}   # 関数 -> 範囲の半幅


def make_config(function_type, half_width, seed, settings):
    pso = {"num_optiter": NUM_STEP, "num_particle": NUM_PARTICLE, "maximize": False,
           "windowsize_residual": 5, "tolerance_residual": -1.0,    # 収束の判定で止めない
           "result_dir": "result_PSO", "filename_output": "output_PSO.dat", "filename_global": "output_global.dat"}
    pso.update(settings)
    return {
        "adapter": {"kind_adapter": "simple_function"},
        "optimizer": {"kind_optimizer": "PSO", "seed": seed},
        "objectives": {"num_objectives": 1},
        "parameter_optimized": {
            "boundary": [{"name": "simple_function",
                          "component": [{"type": f"x{i+1}", "bound_min": -half_width, "bound_max": half_width}
                                        for i in range(NUM_DIM)]}],
            "flag_penalty": False},
        "simple_function": {"flag_output": False, "function_type": function_type},
        "PSO": pso,
    }


def run_one(job):
    work, function_type, half_width, seed, settings = job
    os.makedirs(work)
    with open(os.path.join(work, "borealis.yml"), "w") as f:
        yaml.safe_dump(make_config(function_type, half_width, seed, settings), f, sort_keys=False)
    result = subprocess.run([sys.executable, os.path.join(ROOT, "src", "borealis.py"), "-file", "borealis.yml"],
                            cwd=work, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{work}: {result.stdout}{result.stderr}")
    rows = []
    with open(os.path.join(work, "result_PSO", "output_global.dat")) as f:
        next(f)
        for line in f:
            rows.append([float(v) for v in line.split(",") if v.strip()])
    best = np.minimum.accumulate(np.array(rows)[:, 2])                  # それまでの最良
    inertia = [float(line.split("Inertia:")[1].split(",")[0]) for line in result.stdout.splitlines() if "Inertia:" in line]
    return best, np.array(inertia) if inertia else np.full(NUM_STEP, settings.get("inertia", np.nan))


def main():
    num_thread = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    os.makedirs(DATA, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="borealis_pso_schedule_")
    try:
        jobs, keys = [], []
        for function_type, half_width in FUNCTIONS.items():
            for name, settings in SETTINGS:
                for s in range(NSEED):
                    keys.append((function_type, name))
                    jobs.append((os.path.join(tmp, function_type, name, str(s)), function_type, half_width, SEED0 + s, settings))
        with ThreadPoolExecutor(num_thread) as executor:
            results = list(executor.map(run_one, jobs))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    names = [name for name, _ in SETTINGS]
    summary = ["# function setting median_final mean_final min_final max_final count_below_1 count_below_1e-3"]
    for function_type in FUNCTIONS:
        best = {n: np.array([r[0] for k, r in zip(keys, results) if k == (function_type, n)]) for n in names}
        inertia = {n: np.array([r[1] for k, r in zip(keys, results) if k == (function_type, n)]) for n in names}
        header = "# step " + " ".join(names)
        steps = np.arange(1, NUM_STEP + 1)
        np.savetxt(os.path.join(DATA, f"pso_schedule_{function_type}.dat"),
                   np.column_stack([steps] + [np.median(best[n], axis=0) for n in names]),
                   header=f"PSO weight schedules, {function_type} in {NUM_DIM} dimensions, {NUM_PARTICLE} particles, "
                          f"median over {NSEED} seeds of the best so far\n" + header[2:], fmt="%.6e")
        np.savetxt(os.path.join(DATA, f"pso_schedule_{function_type}_inertia.dat"),
                   np.column_stack([steps] + [np.median(inertia[n], axis=0) for n in names]),
                   header=f"PSO weight schedules, {function_type}: median over {NSEED} seeds of the inertia weight w\n"
                          + header[2:], fmt="%.6e")
        for n in names:
            final = best[n][:, -1]
            summary.append(f"{function_type} {n} {np.median(final):.6e} {final.mean():.6e} {final.min():.6e} "
                           f"{final.max():.6e} {np.sum(final < 1.0)} {np.sum(final < 1.0e-3)}")
    with open(os.path.join(DATA, "pso_schedule_summary.dat"), "w") as f:
        f.write("\n".join(summary) + "\n")
    print("\n".join(summary))


if __name__ == "__main__":
    main()
