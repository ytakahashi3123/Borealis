# 設定ファイルのキーの検査のテスト（既知の問題 4）
import glob
import os

import yaml

from conftest import ROOT, sphere_config
from config_check.config_check import check_config


def test_clean_config_has_no_warning():
    assert check_config(sphere_config("PSO")) == []
    assert check_config(sphere_config("ABC")) == []
    config = sphere_config("PSO", inertia_schedule="adaptive", inertia_max=0.9, inertia_min=0.4,
                           coefficient_schedule="linear", cognitive_coef_initial=2.5, cognitive_coef_final=0.5,
                           social_coef_initial=0.5, social_coef_final=2.5)
    config["simple_function"]["function_type"] = "rastrigin"
    assert check_config(config) == []
    assert check_config(sphere_config("ABC", num_objectives=2, maximize=[False, False], num_archive=20,
                                      windowsize_archive=5, tolerance_archive=0.0)) == []


def test_unknown_and_obsolete_keys():
    config = sphere_config("PSO")
    config["PSO"]["num_particles"] = 10          # 綴りの誤り
    config["PSO"]["tolerance"] = 1.0e-5          # 読まれない古い名前
    config["parameter_optimized"]["boundary"][0]["component"][0]["bound_maxx"] = 1
    config["mystery"] = {}
    warnings = "\n".join(check_config(config))
    assert "PSO.num_particles: unknown key" in warnings
    assert "PSO.tolerance: not read; use PSO.tolerance_residual" in warnings
    assert "component[0].bound_maxx" in warnings
    assert "unknown section 'mystery'" in warnings


def test_old_spelling_is_reported():
    config = sphere_config("ABC")
    abc = config["ABC"]
    abc["vist_limit"] = abc.pop("visit_limit")
    abc["num_onlook_bee"] = abc.pop("num_onlook_bees")
    warnings = "\n".join(check_config(config))
    assert "ABC.vist_limit: old spelling" in warnings
    assert "ABC.num_onlook_bee: old spelling" in warnings


def test_unselected_sections_are_not_checked():
    config = sphere_config("PSO")
    config["ABC"] = {"anything": 1}
    assert check_config(config) == []


def test_repository_configs_have_no_unknown_key():
    # 同梱の borealis.yml に「知らないキー」が無いこと（キーの一覧の漏れの検出）
    files = glob.glob(os.path.join(ROOT, "testcase", "*", "**", "borealis.yml"), recursive=True)
    files += glob.glob(os.path.join(ROOT, "report", "verification", "*", "borealis.yml"))
    files = [f for f in files if "/result_" not in f and "/case" not in os.path.basename(os.path.dirname(f))]
    assert files
    for filename in files:
        with open(filename) as f:
            config = yaml.safe_load(f)
        unknown = [w for w in check_config(config) if "unknown" in w]
        assert unknown == [], filename
