#!/usr/bin/env python3
"""レポートの検証ケース (report/verification/*) を走らせる / Run the verification cases of the report.

乱数の種は各ケースの borealis.yml の optimizer.seed で固定してあるので、逐次実行では毎回同じ答えになる。

使い方:  python3 report/run_verification.py [ケース名 ...]   (省略時はすべて)
"""
import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "report", "verification")


def run(name):
    work = os.path.join(CASES, name)
    # ベイズ最適化のケースは bayesian-optimization が無ければ飛ばす
    if name.startswith("bo_") and importlib.util.find_spec("bayes_opt") is None:
        print(f"{name}: skipped (bayesian-optimization is not installed)")
        return 0
    with open(os.path.join(work, "log_borealis"), "w") as log:
        rc = subprocess.call([sys.executable, os.path.join(ROOT, "src", "borealis.py"), "-file", "borealis.yml"],
                             cwd=work, stdout=log, stderr=subprocess.STDOUT)
    print(f"{name}: {'ok' if rc == 0 else 'FAILED (rc=%d, see log_borealis)' % rc}")
    return rc


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(d for d in os.listdir(CASES) if os.path.isdir(os.path.join(CASES, d)))
    sys.exit(max(run(n) for n in names))
