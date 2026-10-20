#!/usr/bin/env python3
"""Borealis のレポート用の図を作る / Build the figures of the Borealis report.

検証ケース (report/verification/*) を走らせたあとの結果と、report/data/ の測定値を読んで、
report/figure/*.png を書き出す。先に次を実行しておくこと。

    python3 report/run_verification.py

使い方:  python3 report/make_figures.py [出力先ディレクトリ]
"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIF = os.path.join(ROOT, "report", "verification")
DATA = os.path.join(ROOT, "report", "data")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "report", "figure")

plt.rcParams.update({
    "figure.dpi": 140,
    "savefig.dpi": 140,
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "legend.frameon": False,
    "axes.titlesize": 10,
})
COLOR_EXACT = "k"
COLOR_A, COLOR_B, COLOR_C = "#1f77b4", "#d62728", "#2ca02c"
COLOR_D = "#9467bd"
SLOT_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b"]

# 検証の目的関数: f_k(x) = |x - c_k|^2, c_k = 2(k-1)(1,...,1), x は 5 次元
NUM_DIM = 5
C_NORM = 2.0*np.sqrt(NUM_DIM)   # |c_2 - c_1|


def read_tecplot_rows(filename):
    """'Variables=' の行と 'zone' の行を飛ばして、カンマ区切りの数値の行を読む"""
    rows = []
    with open(filename) as f:
        for line in f:
            s = line.strip()
            if not s or s.lower().startswith(("variables", "zone", "i=")):
                continue
            rows.append([float(v) for v in s.split(",") if v.strip()])
    return rows


def fig_convergence():
    """単目的: PSO の世代ごとの最良値と、それまでの最良値。ABC の各ステップの最良値"""
    pso = np.array(read_tecplot_rows(os.path.join(VERIF, "pso_sphere", "result_PSO", "output_global.dat")))
    abc = np.array(read_tecplot_rows(os.path.join(VERIF, "abc_sphere", "result_ABC", "output_global.dat")))
    step_pso, f_pso = pso[:, 0], pso[:, 2]
    step_abc, f_abc = abc[:, 0], abc[:, 2]
    # 各ステップの食料源の中の最良（output_ABC.dat。偵察蜂が最良の食料源を捨てると悪化する）
    hist = read_tecplot_rows(os.path.join(VERIF, "abc_sphere", "result_ABC", "output_ABC.dat"))
    num_bees = len(hist) // len(step_abc)
    f_abc_population = np.array(hist)[:, -2].reshape(len(step_abc), num_bees).min(axis=1)

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.6))
    ax = axes[0]
    ax.semilogy(step_pso, f_pso, "-", color=COLOR_A, lw=1.0, label="PSO, best of each step (output_global.dat)")
    ax.semilogy(step_pso, np.minimum.accumulate(f_pso), "--", color=COLOR_A, lw=1.0, label="PSO, best so far")
    ax.semilogy(step_abc, f_abc_population, ":", color=COLOR_B, lw=1.0, label="ABC, best food source of each step")
    ax.semilogy(step_abc, f_abc, "-", color=COLOR_B, lw=1.0, label="ABC, best so far (output_global.dat)")
    ga_file = os.path.join(VERIF, "ga_sphere", "result_GA", "output_global.dat")
    ga = np.array(read_tecplot_rows(ga_file)) if os.path.exists(ga_file) else None
    if ga is not None:
        ax.semilogy(ga[:, 0], ga[:, 2], "-", color=COLOR_D, lw=1.0, label="GA, best of each generation (output_global.dat)")
    ax.set_xlabel("step")
    ax.set_ylabel(r"$f(\mathbf{x}) = |\mathbf{x}|^2$ (exact minimum 0)")
    ax.set_title("Sphere function in 5 dimensions, $-10 \\leq x_i \\leq 10$")
    ax.legend(fontsize=7, loc="upper right")

    # 評価の回数に対するそれまでの最良（PSO: 20 粒子、ABC: 初期 20 + 1 ステップ 40、偵察蜂の評価は数えない、BO: 1 回ずつ）
    ax = axes[1]
    num_particle, num_bee = 20, 20
    ax.semilogy(step_pso*num_particle, np.minimum.accumulate(f_pso), "-", color=COLOR_A, lw=1.0, label="PSO (20 particles)")
    ax.semilogy(num_bee + step_abc*2*num_bee, f_abc, "-", color=COLOR_B, lw=1.0, label="ABC (20 + 20 bees)")
    if ga is not None:
        ax.semilogy((ga[:, 0] + 1)*20, ga[:, 2], "-", color=COLOR_D, lw=1.0, label="GA (20 individuals)")
        print("convergence.png: GA", int(ga[-1, 0]), "generations, best", ga[-1, 2])
    bo_file = os.path.join(VERIF, "bo_sphere", "result_bopt", "output_bopt.dat")
    if os.path.exists(bo_file):
        bo = np.loadtxt(bo_file, delimiter=",", skiprows=1)
        ax.semilogy(bo[:, -1], np.minimum.accumulate(bo[:, -2]), "-", color=COLOR_C, lw=1.2,
                    label="Bayesian optimization (EI)")
        print("convergence.png: BO", len(bo), "evaluations, best", bo[:, -2].min())
    ax.set_xscale("log")
    ax.set_xlabel("number of evaluations")
    ax.set_ylabel("best so far")
    ax.set_title("Best so far against the number of evaluations")
    ax.legend(fontsize=7, loc="lower left")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "convergence.png"))
    plt.close(fig)
    print("convergence.png: PSO", len(step_pso), "steps, final", f_pso[-1], "; ABC", len(step_abc), "steps, final", f_abc[-1])


def fig_pareto():
    """2 目的: 各ステップのアーカイブと厳密なパレートフロント sqrt(f1) + sqrt(f2) = |c|"""
    rows = read_tecplot_rows(os.path.join(VERIF, "pso_pareto", "result_PSO", "output_global.dat"))
    a = np.array(rows)
    step, f1, f2 = a[:, 0], a[:, 2], a[:, 3]
    x = a[:, 4:4+NUM_DIM]
    # パレート集合 (c_1 と c_2 を結ぶ線分) からの外れ: |x| + |x - c_2| - |c_2| >= 0 (三角不等式)
    dev = np.linalg.norm(x, axis=1) + np.linalg.norm(x - 2.0, axis=1) - C_NORM
    steps = np.unique(step)
    dev_mean = np.array([dev[step == s].mean() for s in steps])
    dev_max = np.array([dev[step == s].max() for s in steps])
    size = np.array([np.sum(step == s) for s in steps])

    ga_rows = None
    ga_file = os.path.join(VERIF, "ga_pareto", "result_GA", "output_global.dat")
    if os.path.exists(ga_file):
        g = np.array(read_tecplot_rows(ga_file))
        g_x = g[:, 4:4+NUM_DIM]
        g_dev = np.linalg.norm(g_x, axis=1) + np.linalg.norm(g_x - 2.0, axis=1) - C_NORM
        g_steps = np.unique(g[:, 0])
        ga_rows = (g, g_dev, g_steps)

    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.4))
    ax = axes[0]
    t = np.linspace(0.0, 1.0, 200)
    ax.plot((C_NORM*t)**2, (C_NORM*(1.0-t))**2, "-", color=COLOR_EXACT, lw=1.0, label="exact Pareto front")
    early = step <= 10
    ax.plot(f1[early], f2[early], ".", color="0.7", ms=3, label="PSO archive, steps 1--10")
    last = step == steps[-1]
    ax.plot(f1[last], f2[last], "o", color=COLOR_B, ms=3.5, mfc="none", label=f"PSO archive, step {int(steps[-1])}")
    if ga_rows is not None:
        g, g_dev, g_steps = ga_rows
        g_last = g[:, 0] == g_steps[-1]
        ax.plot(g[g_last, 2], g[g_last, 3], "s", color=COLOR_D, ms=3.0, mfc="none", label=f"GA front, generation {int(g_steps[-1])}")
        print("pareto.png: GA front", int(np.sum(g_last)), "points, mean deviation", g_dev[g_last].mean(), ", max", g_dev[g_last].max())
    ax.set_xlim(0, 25)
    ax.set_ylim(0, 25)
    ax.set_xlabel(r"$f_1 = |\mathbf{x}|^2$")
    ax.set_ylabel(r"$f_2 = |\mathbf{x} - 2\mathbf{1}|^2$")
    ax.set_aspect("equal")
    ax.legend(fontsize=7.5)
    ax.set_title("Objective space")

    ax = axes[1]
    ax.semilogy(steps, dev_max, "-", color=COLOR_B, lw=1.0, label="PSO, max over archive")
    ax.semilogy(steps, dev_mean, "-", color=COLOR_A, lw=1.0, label="PSO, mean over archive")
    if ga_rows is not None:
        g, g_dev, g_steps = ga_rows
        ax.semilogy(g_steps, [g_dev[g[:, 0] == s_].mean() for s_ in g_steps], "-", color=COLOR_D, lw=1.0, label="GA, mean over front")
    ax.set_xlabel("step")
    ax.set_ylabel(r"$|\mathbf{x}| + |\mathbf{x} - 2\mathbf{1}| - 2\sqrt{5}$")
    ax.set_title("Distance from the Pareto set")
    ax2 = ax.twinx()
    ax2.plot(steps, size, ":", color="0.4", lw=1.0)
    ax2.set_ylabel("archive size (dotted)")
    ax2.grid(False)
    ax.legend(fontsize=7.5, loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "pareto.png"))
    plt.close(fig)
    print("pareto.png: final archive", int(size[-1]), "points, max deviation", dev_max[-1], ", mean", dev_mean[-1])


def read_timeline(filename, has_slot):
    cases, slots, t0, t1 = [], [], [], []
    with open(filename) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            v = line.split()
            cases.append(v[0])
            if has_slot:
                slots.append(int(v[1]))
                t0.append(float(v[3])); t1.append(float(v[4]))
            else:
                t0.append(float(v[1])); t1.append(float(v[2]))
    t0, t1 = np.array(t0), np.array(t1)
    tmin = t0.min()
    return cases, slots, t0 - tmin, t1 - tmin


def fig_parallel():
    """並列評価 (PSO.num_parallel = 3) のタイムライン: ダミーの MPI コードと SU2+preCICE"""
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.4))
    cases, slots, t0, t1 = read_timeline(os.path.join(DATA, "parallel_dummy.dat"), True)
    order = np.argsort([int(c[-4:]) for c in cases])
    ax = axes[0]
    for k, i in enumerate(order):
        ax.barh(k, t1[i]-t0[i], left=t0[i], color=SLOT_COLORS[slots[i] % len(SLOT_COLORS)], height=0.7)
    for s in sorted(set(slots)):
        ax.barh(np.nan, 0, color=SLOT_COLORS[s], label=f"slot {s} (cores {2*s},{2*s+1})")
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([str(int(cases[i][-4:])) for i in order], fontsize=6.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 20.5)
    ax.set_xlabel("elapsed time [s]")
    ax.set_ylabel("evaluation (case ID)")
    ax.set_title("Dummy MPI code, 2 s per evaluation")
    ax.legend(fontsize=7, loc="upper right")

    cases, _, t0, t1 = read_timeline(os.path.join(DATA, "parallel_su2.dat"), False)
    order = np.argsort([int(c[-4:]) for c in cases])
    ax = axes[1]
    for k, i in enumerate(order):
        ax.barh(k, t1[i]-t0[i], left=t0[i], color=SLOT_COLORS[k // 3 % len(SLOT_COLORS)], height=0.7)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([str(int(cases[i][-4:])) for i in order], fontsize=6.5)
    ax.invert_yaxis()
    ax.set_xlabel("elapsed time [s]")
    ax.set_title("SU2 + preCICE, 2 cores per case")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "parallel_timeline.png"))
    plt.close(fig)
    print("parallel_timeline.png: SU2", len(t0), "cases")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    fig_convergence()
    fig_pareto()
    fig_parallel()
