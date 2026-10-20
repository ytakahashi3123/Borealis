# 手法を通しで走らせるテスト（simple_function = ずらした球関数。解析解が分かっている）
import os

import numpy as np
import pytest

from conftest import read_global, run_borealis, sphere_config


def test_pso_converges_and_is_reproducible(workdir):
    rc, out = run_borealis(workdir, sphere_config("PSO"))
    assert rc == 0, out
    first = read_global(workdir, "result_PSO")
    assert first[:, 2].min() < 1.0e-6                       # 厳密な最小は 0
    rc, out = run_borealis(workdir, sphere_config("PSO"))     # 同じ種なら同じ答え
    assert rc == 0, out
    assert np.array_equal(first, read_global(workdir, "result_PSO"))


def test_pso_concurrent_evaluation_matches_serial(workdir, tmp_path_factory):
    # スレッドで同時に評価しても、答えは逐次と同じ（PSO の更新の順序は変わらない）
    rc, out = run_borealis(workdir, sphere_config("PSO"))
    assert rc == 0, out
    serial = read_global(workdir, "result_PSO")
    other = str(tmp_path_factory.mktemp("parallel"))
    rc, out = run_borealis(other, sphere_config("PSO", num_parallel=4))
    assert rc == 0, out
    assert "Number of concurrent evaluations: 4" in out
    assert np.array_equal(serial, read_global(other, "result_PSO"))


def test_pso_maximize_applies_sign(workdir):
    # simple_function は符号を掛ける。最大化では記録される値が -f になる
    config = sphere_config("PSO", maximize=True, num_optiter=5)
    rc, out = run_borealis(workdir, config)
    assert rc == 0, out
    assert (read_global(workdir, "result_PSO")[:, 2] < 0.0).all()


def test_pso_maximize_list_length_is_checked(workdir):
    rc, out = run_borealis(workdir, sphere_config("PSO", maximize=[False, False], num_optiter=3))
    assert rc != 0 and "PSO.maximize has 2 entries" in out


def test_pso_two_objectives_reach_pareto_set(workdir):
    # f1 = |x|^2, f2 = |x - 2|^2。Pareto 集合は 0 と 2 を結ぶ線分で、|x| + |x - 2| - |2| = 0
    config = sphere_config("PSO", num_objectives=2, maximize=[False, False], num_particle=30, num_optiter=60,
                           windowsize_archive=2, tolerance_archive=1.0e-12)
    rc, out = run_borealis(workdir, config)
    assert rc == 0, out
    data = read_global(workdir, "result_PSO")
    last = data[data[:, 0] == data[:, 0].max()]
    x = last[:, 4:]
    deviation = np.linalg.norm(x, axis=1) + np.linalg.norm(x - 2.0, axis=1) - 2.0*np.sqrt(x.shape[1])
    assert len(last) >= 5 and deviation.mean() < 0.5


def test_abc_best_so_far_is_monotone(workdir):
    # output_global.dat はそれまでの最良（以前はそのステップの食料源の最良で、悪化しえた。既知の問題 16）
    rc, out = run_borealis(workdir, sphere_config("ABC"))
    assert rc == 0, out
    best = read_global(workdir, "result_ABC")[:, 2]
    assert np.all(np.diff(best) <= 0.0) and best[-1] < 1.0e-2


def test_abc_rejects_several_objectives(workdir):
    rc, out = run_borealis(workdir, sphere_config("ABC", num_objectives=2))
    assert rc != 0 and "single objective only" in out


def test_abc_accepts_old_key_spelling(workdir):
    config = sphere_config("ABC", num_optiter=5)
    abc = config["ABC"]
    abc["vist_limit"] = abc.pop("visit_limit")
    abc["num_onlook_bee"] = abc.pop("num_onlook_bees")
    rc, out = run_borealis(workdir, config)
    assert rc == 0, out
    assert "old spelling" in out


def test_invalid_adapter_stops(workdir):
    config = sphere_config("PSO")
    config["adapter"]["kind_adapter"] = "no_such_adapter"
    rc, out = run_borealis(workdir, config)
    assert rc != 0 and "invalid adapter" in out


def test_abc_concurrent_evaluation(workdir, tmp_path_factory):
    # ABC の並列評価: 雇用蜂は段の始まりの食料源から候補を作るので、逐次とは答えが変わるが、
    # 並列の数（2 でも 4 でも）によらず同じ答えになり、それまでの最良は単調に下がる
    rc, out = run_borealis(workdir, sphere_config("ABC", num_parallel=2))
    assert rc == 0, out
    assert "Number of concurrent evaluations: 2" in out
    two = read_global(workdir, "result_ABC")
    assert np.all(np.diff(two[:, 2]) <= 0.0) and two[-1, 2] < 1.0e-2
    other = str(tmp_path_factory.mktemp("parallel4"))
    rc, out = run_borealis(other, sphere_config("ABC", num_parallel=4))
    assert rc == 0, out
    assert np.array_equal(two, read_global(other, "result_ABC"))
