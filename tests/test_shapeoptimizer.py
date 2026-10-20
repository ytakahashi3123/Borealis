# shapeoptimizer の並列評価を、MPI を使わないダミーの外部コードで通しで確かめる
import os

import numpy as np
import pytest

from conftest import read_global, run_borealis

DUMMY_SCRIPT = """#!/bin/sh
# ダミーの外部コード: 変位から力を作り、割り当てられたコアを書き出す
cd optimization
python3 - <<'PYEOF'
import os, numpy as np
d = np.loadtxt('displacements.dat', ndmin=2)
if os.environ.get('DUMMY_FAIL'):
    raise SystemExit(1)
with open('../cpuset.txt', 'w') as f:
    f.write(os.environ.get('BOREALIS_CPU_SET', '') + '\\n')
with open('forces.dat', 'w') as f:
    f.write(f"{np.sum(d**2):.10e} 0.0\\n{np.sum(np.abs(d)):.10e}\\n")
PYEOF
"""


def _config(template, num_objectives, num_parallel):
    return {
        "adapter": {"kind_adapter": "shapeoptimizer"},
        "optimizer": {"kind_optimizer": "PSO", "seed": 7},
        "objectives": {"num_objectives": num_objectives},
        "parameter_optimized": {
            "boundary": [{"name": f"Coord{k}", "component": [{"type": "x", "bound_min": -1, "bound_max": 1},
                                                              {"type": "y", "bound_min": -1, "bound_max": 1}]}
                         for k in range(2)],
            "flag_penalty": False,
        },
        "PSO": {"num_optiter": 3, "num_particle": 4, "num_parallel": num_parallel,
                "maximize": [False]*num_objectives, "inertia": 0.5, "cognitive_coef": 1.0, "social_coef": 1.0,
                "windowsize_residual": 50, "result_dir": "result_PSO",
                "filename_output": "output_PSO.dat", "filename_global": "output_global.dat"},
        "shapeoptimizer": {"work_dir": "work_shapeoptimizer", "case_dir": "case", "step_digit": 4,
                           "directory_path_specify": "manual", "manual_path": template,
                           "cmd_code": "./run_dummy.sh", "result_dir": "result_shapeoptimizer",
                           "in_sequential": False, "work_dir_series": "optimization",
                           "filename_forces": "forces.dat", "filename_displacements": "displacements.dat",
                           "step_digit_series": 5, "num_cpu_per_case": 1, "polling_interval": 0.05,
                           "penalty_failure": 1.0e10},
    }


@pytest.fixture
def template(tmp_path):
    path = tmp_path / "template"
    (path / "optimization").mkdir(parents=True)
    script = path / "run_dummy.sh"
    script.write_text(DUMMY_SCRIPT)
    script.chmod(0o755)
    return str(path)


@pytest.mark.parametrize("num_objectives", [1, 2])
def test_shapeoptimizer_concurrent(tmp_path, template, num_objectives):
    workdir = tmp_path / "run"
    workdir.mkdir()
    rc, out = run_borealis(str(workdir), _config(template, num_objectives, num_parallel=2))
    assert rc == 0, out
    data = read_global(str(workdir), "result_PSO")
    assert np.isfinite(data[:, 2]).all() and data.shape[1] == 2 + num_objectives + 4
    # 各ケースに割り当てたコアは、このプロセスに許されたコアの中から取る（既知の問題 20）
    allowed = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else list(range(os.cpu_count()))
    cases = sorted((workdir / "work_shapeoptimizer").glob("case_rank*"))
    assert len(cases) == 12
    cpus = {int((c / "cpuset.txt").read_text()) for c in cases}
    assert cpus <= set(allowed[:2])


def test_shapeoptimizer_failure_returns_penalty(tmp_path, template, monkeypatch):
    monkeypatch.setenv("DUMMY_FAIL", "1")
    workdir = tmp_path / "run"
    workdir.mkdir()
    rc, out = run_borealis(str(workdir), _config(template, 2, num_parallel=2))
    assert rc == 0, out
    assert (read_global(str(workdir), "result_PSO")[:, 2] == 1.0e10).all()


@pytest.mark.parametrize("kind_optimizer", ["GA", "ABC"])
def test_shapeoptimizer_concurrent_with_ga_and_abc(tmp_path, template, kind_optimizer):
    # GA と ABC でも、<kind_optimizer>.num_parallel で外部コードを同時に評価する
    config = _config(template, 2 if kind_optimizer == "GA" else 1, num_parallel=2)
    config.pop("PSO")
    config["optimizer"]["kind_optimizer"] = kind_optimizer
    if kind_optimizer == "GA":
        config["GA"] = {"num_generation": 2, "num_population": 4, "num_parallel": 2, "maximize": [False, False],
                        "result_dir": "result_GA", "filename_output": "output_GA.dat", "filename_global": "output_global.dat"}
    else:
        config["ABC"] = {"num_optiter": 2, "num_employ_bees": 4, "num_onlook_bees": 4, "visit_limit": 5,
                         "tolerance": 1.0e-14, "num_parallel": 2, "result_dir": "result_ABC",
                         "filename_output": "output_ABC.dat", "filename_global": "output_global.dat"}
    workdir = tmp_path / "run"
    workdir.mkdir()
    rc, out = run_borealis(str(workdir), config)
    assert rc == 0, out
    assert "Number of concurrent evaluations: 2" in out
    data = read_global(str(workdir), f"result_{kind_optimizer}")
    assert np.isfinite(data[:, 2]).all()
    allowed = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else list(range(os.cpu_count()))
    cases = sorted((workdir / "work_shapeoptimizer").glob("case_rank*"))
    assert {int((c / "cpuset.txt").read_text()) for c in cases} <= set(allowed[:2])
