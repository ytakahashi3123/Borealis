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


def test_abc_two_objectives_reach_pareto_set(workdir):
    # 多目的 ABC: 各ステップのアーカイブは互いに支配しない点だけで、num_archive を超えない。
    # 最後のアーカイブは Pareto 集合（0 と 2 を結ぶ線分）に近い。同じ種なら同じ答え
    config = sphere_config("ABC", num_objectives=2, maximize=[False, False], num_optiter=80, num_archive=15)
    rc, out = run_borealis(workdir, config)
    assert rc == 0, out
    data = read_global(workdir, "result_ABC")
    for step in np.unique(data[:, 0]):
        f = data[data[:, 0] == step][:, 2:4]
        assert len(f) <= 15
        for a in f:
            assert not np.any(np.all(f <= a, axis=1) & np.any(f < a, axis=1))
    last = data[data[:, 0] == data[:, 0].max()]
    x = last[:, 4:]
    deviation = np.linalg.norm(x, axis=1) + np.linalg.norm(x - 2.0, axis=1) - 2.0*np.sqrt(x.shape[1])
    assert len(last) == 15 and deviation.mean() < 0.5
    rc, out = run_borealis(workdir, config)
    assert rc == 0, out
    assert np.array_equal(data, read_global(workdir, "result_ABC"))


def test_abc_two_objectives_concurrent_and_maximize(workdir):
    # 多目的でも並列評価と最大化（目的ごとのリスト）が通る。最大化した目的は -f が記録される
    config = sphere_config("ABC", num_objectives=2, maximize=[False, True], num_optiter=10, num_parallel=3)
    rc, out = run_borealis(workdir, config)
    assert rc == 0, out
    data = read_global(workdir, "result_ABC")
    assert (data[:, 2] >= 0.0).all() and (data[:, 3] < 0.0).all()


def test_abc_maximize_list_length_is_checked(workdir):
    rc, out = run_borealis(workdir, sphere_config("ABC", maximize=[False, False], num_optiter=3))
    assert rc != 0 and "ABC.maximize has 2 entries" in out


def _pso_coefficients(out):
    # ログの "Inertia: w, Cognitive coef: c1, Social coef: c2" をステップ順に読む
    rows = []
    for line in out.splitlines():
        if "Inertia:" in line:
            rows.append([float(part.split(":")[1]) for part in line.split(",")[1:]])
    return np.array(rows)


def test_pso_linear_schedules(workdir):
    # 慣性の重みは 0.9 から 0.4 へ、c1 は 2.5 から 0.5 へ、c2 は 0.5 から 2.5 へ線形に変わる
    config = sphere_config("PSO", num_optiter=11, tolerance_residual=-1.0,
                           inertia_schedule="linear", coefficient_schedule="linear")
    for key in ("inertia", "cognitive_coef", "social_coef"):
        del config["PSO"][key]
    rc, out = run_borealis(workdir, config)
    assert rc == 0, out
    coef = _pso_coefficients(out)
    assert coef.shape == (11, 3)
    assert np.allclose(coef[:, 0], np.linspace(0.9, 0.4, 11), atol=1e-5)
    assert np.allclose(coef[:, 1], np.linspace(2.5, 0.5, 11), atol=1e-5)
    assert np.allclose(coef[:, 2], np.linspace(0.5, 2.5, 11), atol=1e-5)


def test_pso_adaptive_inertia(workdir):
    # 最初のステップはすべての粒子が個人の最良を更新するので w = inertia_max。w は常に [inertia_min, inertia_max]。
    # 球関数でも収束する
    config = sphere_config("PSO", num_optiter=100, inertia_schedule="adaptive", inertia_max=0.8, inertia_min=0.3,
                           cognitive_coef=1.49618, social_coef=1.49618)
    del config["PSO"]["inertia"]
    rc, out = run_borealis(workdir, config)
    assert rc == 0, out
    coef = _pso_coefficients(out)
    assert coef[0, 0] == pytest.approx(0.8)
    assert (coef[:, 0] >= 0.3 - 1e-12).all() and (coef[:, 0] <= 0.8 + 1e-12).all()
    assert len(np.unique(coef[:, 0])) > 2
    assert read_global(workdir, "result_PSO")[:, 2].min() < 1.0e-6


def test_pso_invalid_schedule_stops(workdir):
    rc, out = run_borealis(workdir, sphere_config("PSO", inertia_schedule="cosine", num_optiter=3))
    assert rc != 0 and "PSO.inertia_schedule must be" in out


def test_rastrigin_function(workdir):
    # Rastrigin: 最小値 0 は x_i = 0（目的 k では 2k）。整数の格子点の近くに局所解がある
    config = sphere_config("PSO", num_optiter=3)
    config["simple_function"]["function_type"] = "rastrigin"
    from adapter_template.adapter_simple_function import adapter_simple_function
    class _MPI:
        rank, size, flag_mpi = 0, 1, False
    adapter = adapter_simple_function(_MPI())
    adapter.initial_settings(config)
    assert adapter.function(np.zeros(3))[0] == pytest.approx(0.0)
    assert adapter.function(np.array([1.0, 0.0, 0.0]))[0] == pytest.approx(1.0)
    assert adapter.function(np.array([0.5, 0.0, 0.0]))[0] == pytest.approx(20.25)
    rc, out = run_borealis(workdir, config)
    assert rc == 0, out


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
