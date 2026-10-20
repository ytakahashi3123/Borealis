# Borealis のテスト / Tests of Borealis
#
#   cd <repository> && python3 -m pytest tests
#
# src/ を import の道に足し、Borealis を 1 回走らせるための道具を用意する。
import os
import subprocess
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def sphere_config(kind_optimizer="PSO", num_objectives=1, num_dimension=3, seed=12345, **optimizer_settings):
    """simple_function（ずらした球関数）の設定を作る"""
    config = {
        "adapter": {"kind_adapter": "simple_function"},
        "optimizer": {"kind_optimizer": kind_optimizer, "seed": seed},
        "objectives": {"num_objectives": num_objectives},
        "parameter_optimized": {
            "boundary": [{"name": "simple_function",
                          "component": [{"type": f"x{i+1}", "bound_min": -10, "bound_max": 10}
                                        for i in range(num_dimension)]}],
            "flag_penalty": False,
        },
        "simple_function": {"flag_output": False},
    }
    if kind_optimizer == "PSO":
        settings = {"num_optiter": 60, "num_particle": 12, "maximize": False, "inertia": 0.5,
                    "cognitive_coef": 1.0, "social_coef": 1.0, "windowsize_residual": 5,
                    "tolerance_residual": 1.0e-12, "result_dir": "result_PSO",
                    "filename_output": "output_PSO.dat", "filename_global": "output_global.dat"}
    elif kind_optimizer == "GA":
        settings = {"num_generation": 40, "num_population": 12, "maximize": False,
                    "windowsize_residual": 5, "tolerance_residual": 1.0e-12, "result_dir": "result_GA",
                    "filename_output": "output_GA.dat", "filename_global": "output_global.dat"}
    elif kind_optimizer == "ABC":
        settings = {"num_optiter": 60, "num_employ_bees": 12, "num_onlook_bees": 12, "visit_limit": 10,
                    "maximize": False, "tolerance": 1.0e-14, "result_dir": "result_ABC",
                    "filename_output": "output_ABC.dat", "filename_global": "output_global.dat"}
    else:
        settings = {"model_type": "GP", "normalize_Y": True, "maximize": False, "acquisition_type": "EI",
                    "acquisition_xi": 0.01, "initial_design_numdata": 5, "num_optiter": 20,
                    "result_dir": "result_bopt", "filename_output": "output_bopt.dat",
                    "flag_image_convergence": True, "filename_image_convergence": "convergence.png"}
    settings.update(optimizer_settings)
    config[kind_optimizer] = settings
    return config


def run_borealis(workdir, config, command_prefix=None, timeout=300):
    """workdir に borealis.yml を書いて Borealis を走らせ、(終了コード, 出力) を返す"""
    with open(os.path.join(workdir, "borealis.yml"), "w") as f:
        yaml.safe_dump(config, f, sort_keys=False)
    command = (command_prefix or []) + [sys.executable, os.path.join(SRC, "borealis.py"), "-file", "borealis.yml"]
    result = subprocess.run(command, cwd=workdir, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout + result.stderr


def read_global(workdir, result_dir):
    """output_global.dat を (ステップ, 目的関数の値の並び) の配列として読む"""
    import numpy as np
    rows = []
    with open(os.path.join(workdir, result_dir, "output_global.dat")) as f:
        next(f)
        for line in f:
            rows.append([float(v) for v in line.split(",") if v.strip()])
    return np.array(rows)


@pytest.fixture
def workdir(tmp_path):
    return str(tmp_path)
