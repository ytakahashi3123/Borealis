# ベイズ最適化（bayesian-optimization）のテスト。ライブラリが無ければ飛ばす
import os

import numpy as np
import pytest

from conftest import run_borealis, sphere_config

pytest.importorskip("bayes_opt")


def _read_bopt(workdir):
    data = np.loadtxt(os.path.join(workdir, "result_bopt", "output_bopt.dat"), delimiter=",", skiprows=1)
    return data[:, :-2], data[:, -2]   # パラメータ, 誤差


def test_bo_converges_and_is_reproducible(workdir):
    rc, out = run_borealis(workdir, sphere_config("Bayesian_optimization"))
    assert rc == 0, out
    x, error = _read_bopt(workdir)
    assert len(error) == 25                      # 初期の 5 点 + 20 回
    assert error.min() < 1.0                     # 3 次元の球関数、厳密な最小は 0（範囲は [-10, 10]^3）
    # 収束の図は matplotlib があるときだけ作る（無ければ警告を出して飛ばす）
    try:
        import matplotlib  # noqa: F401
        assert os.path.exists(os.path.join(workdir, "result_bopt", "convergence.png"))
    except ImportError:
        assert "matplotlib is not installed" in out
    rc, out = run_borealis(workdir, sphere_config("Bayesian_optimization"))
    assert rc == 0, out
    x2, error2 = _read_bopt(workdir)
    assert np.array_equal(error, error2) and np.array_equal(x, x2)


def test_bo_maximize(workdir):
    # |x|^2 を最大化すると範囲の隅（最大 300）へ向かう
    rc, out = run_borealis(workdir, sphere_config("Bayesian_optimization", maximize=True))
    assert rc == 0, out
    _, error = _read_bopt(workdir)
    assert error.max() > 150.0


def test_bo_rejects_unavailable_model(workdir):
    rc, out = run_borealis(workdir, sphere_config("Bayesian_optimization", model_type="RF", num_optiter=1))
    assert rc != 0 and "model_type RF is not available" in out
