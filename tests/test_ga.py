# 遺伝的アルゴリズム（実数値 GA、NSGA-II の世代交代）のテスト
import numpy as np
import pytest

from conftest import read_global, run_borealis, sphere_config
from optimizer_ga.optimizer_ga import optimizer_ga


class _MPI:
    rank, size, flag_mpi = 0, 1, False


def test_operators_stay_in_bounds():
    # SBX と多項式突然変異は範囲の外に出ない
    ga = optimizer_ga(_MPI())
    rng = np.random.default_rng(1)
    np.random.seed(1)
    lower, upper = np.array([-1.0, 0.0, 10.0]), np.array([1.0, 5.0, 10.5])
    for _ in range(500):
        p1, p2 = rng.uniform(lower, upper), rng.uniform(lower, upper)
        c1, c2 = ga.crossover_sbx(p1, p2, lower, upper, 15.0)
        m = ga.mutation_polynomial(c1, lower, upper, 1.0, 20.0)
        for x in (c1, c2, m):
            assert np.all(x >= lower) and np.all(x <= upper)


def test_non_dominated_sort_and_selection():
    ga = optimizer_ga(_MPI())
    scores = np.array([[1.0, 4.0], [2.0, 2.0], [4.0, 1.0], [3.0, 3.0], [5.0, 5.0]])
    assert ga.non_dominated_sort(scores).tolist() == [0, 0, 0, 1, 2]
    selected = ga.environmental_selection(scores, 3)
    assert sorted(selected.tolist()) == [0, 1, 2]
    # 配列の演算で求める第 1 フロント（ABC のアーカイブが使う）は、順位 0 と一致する
    rng = np.random.default_rng(3)
    for _ in range(20):
        scores = rng.integers(0, 5, size=(30, 3)).astype(float)   # 同じ値を含む
        assert np.array_equal(ga.non_dominated_mask(scores), ga.non_dominated_sort(scores) == 0)


def test_ga_converges_monotonically_and_is_reproducible(workdir):
    rc, out = run_borealis(workdir, sphere_config("GA"))
    assert rc == 0, out
    best = read_global(workdir, "result_GA")
    assert np.all(np.diff(best[:, 2]) <= 0.0)          # エリート保存なので最良は悪化しない
    assert best[-1, 2] < 1.0                           # 3 次元、厳密な最小は 0
    rc, out = run_borealis(workdir, sphere_config("GA"))
    assert rc == 0, out
    assert np.array_equal(best, read_global(workdir, "result_GA"))


def test_ga_concurrent_evaluation_matches_serial(workdir, tmp_path_factory):
    rc, out = run_borealis(workdir, sphere_config("GA", num_generation=10))
    assert rc == 0, out
    other = str(tmp_path_factory.mktemp("parallel"))
    rc, out = run_borealis(other, sphere_config("GA", num_generation=10, num_parallel=3))
    assert rc == 0, out
    assert np.array_equal(read_global(workdir, "result_GA"), read_global(other, "result_GA"))


def test_ga_two_objectives_cover_the_front(workdir):
    # NSGA-II はフロント全体に広がる（f1 = |x|^2 は 0 から |2|^2 = 12 まで）
    config = sphere_config("GA", num_objectives=2, maximize=[False, False], num_population=24, num_generation=60)
    rc, out = run_borealis(workdir, config)
    assert rc == 0, out
    data = read_global(workdir, "result_GA")
    last = data[data[:, 0] == data[:, 0].max()]
    x = last[:, 4:]
    deviation = np.linalg.norm(x, axis=1) + np.linalg.norm(x - 2.0, axis=1) - 2.0*np.sqrt(x.shape[1])
    assert deviation.mean() < 0.5
    assert last[:, 2].min() < 1.0 and last[:, 2].max() > 8.0


def test_ga_maximize(workdir):
    rc, out = run_borealis(workdir, sphere_config("GA", maximize=True, num_generation=5))
    assert rc == 0, out
    assert (read_global(workdir, "result_GA")[:, 2] < 0.0).all()


def test_ga_old_keys_are_reported(workdir):
    rc, out = run_borealis(workdir, sphere_config("GA", num_generation=2, mutation_limit=0.1, tolerance=1.0e-5))
    assert rc == 0, out
    assert "GA.mutation_limit: not read" in out and "GA.tolerance: not read" in out
