# Change Log
All notable changes to this project will be documented in this file.

## [1.7.0] - 2026-10-20
公開済みの最後の版は v1.5.0（タグは v1.5.1 まで）。手元の 1.6.0・1.6.1 は公開していない。以下は v1.5.x からの変更をまとめたもの。

### Added
- **並列評価**（`PSO.num_parallel`）: 外部コード自体が MPI で走る場合のために、Borealis を 1 プロセスで起動し、粒子の評価をスレッドで同時に呼ぶ。`shapeoptimizer` は評価ごとにコアの組を割り当て（`num_cpu_per_case`・`cpu_offset`・`cpu_assignment`）、`BOREALIS_CPU_SET` などの環境変数で実行スクリプトに渡す。MPI で起動したランクから外部コードの `mpirun` を起動できない問題（既知の問題 18）の回避策。設計と測定はレポートの「並列化」と「検証」の節。
- **遺伝的アルゴリズム（GA）を実装した**（`kind_optimizer: GA`、`src/optimizer_ga/`）。実数値の GA で、トーナメント選択・SBX 交叉・多項式突然変異・NSGA-II の世代交代（親と子を合わせて非劣解の順位と混雑距離で残す）。単目的ではエリート保存の GA、2 目的以上では NSGA-II になる。MPI での評価の分担、`GA.num_parallel` による並列評価、`optimizer.seed` に対応。1.6 までの試作の GA（`borealis.py` で外してあった）を置き換えたもの。検証ケース `report/verification/ga_sphere`・`ga_pareto`。
- ABC の並列評価（`ABC.num_parallel`）。初期化・追従蜂・偵察蜂は逐次と同じ答え、雇用蜂は段の始まりの食料源から候補を作る（並列のときだけ）。
- **ベイズ最適化を bayesian-optimization（3.x）で書き直した**（GPyOpt は保守が止まり numpy 2 で動かないため。既知の問題 22）。候補を 1 つずつ出して登録する形で回し、PSO・ABC と同じく評価の番号を目的関数に渡す。設定の名前（`acquisition_type`・`initial_design_numdata`・`num_optiter` など）はそのまま。`acquisition_type` は EI・PI（MPI）・LCB（UCB）、`acquisition_xi` を新設。GPyOpt にしか無かった選択肢（GP 以外のモデル、MCMC の獲得関数、獲得関数の図）は無くなった。`optimizer.seed` で再現できる。
- `src/config_check/`: 設定ファイルの知らないキー・読まれるが効かないキー・古い綴りのキーを、起動時に警告する（既知の問題 4）。
- `optimizer.seed`: 乱数の種。各ランクを `seed + rank` で初期化する（既知の問題 11）。
- `parameter_optimized.value_nonfinite`: 目的関数が NaN・無限大のとき、または外部コードが失敗したときに使う値（既定 1e30）。
- `ABC.windowsize_residual`、正しい綴りのキー `ABC.visit_limit`・`ABC.num_onlook_bees`（古い綴りも読む）。
- `tests/`（pytest、42 件）と GitHub Actions の CI（`.github/workflows/ci.yml`、Python 3.9 と 3.12、MPI のテストを含む）。
- `report/`（詳細レポート 日英、設定ファイルの対応表、検証ケース、図）。
- MPI
- `src/optimizer_abc/optimizer_abc.py`: ABCにPSOと同様の`maximize`オプション(最大化/最小化の符号反転`sign_of`の仕組み)を追加。`config['ABC']['maximize']`が未設定の場合は従来通り最小化(`sign_of=1.0`)として動作し、既存設定への影響はない。
- `CLAUDE.md`: リポジトリの規約(YAML config形式、adapter/optimizerの実装パターン、命名規則等)をまとめたガイドを追加。
- `testcase/work_tacode_fortran/work_tacode_iss`, `template/work_tacode_iss`, `reference/iss_tle`: ISS軌道の比較に基づく大気密度推定のトライアルケースを追加。実際のISSのTLE(Celestrak)をSGP4で伝播し、間欠的なGNSS疑似観測とガウス過程回帰(GPR)によりリファレンス軌道(経度・緯度・高度)を再構成するスクリプト`reference/iss_tle/src_py/make_reference_iss.py`を追加。衛星諸元はISS実機相当(質量4.2e5kg、Cd=2.2、代表面積1200m2)とし、`orbit.ctl`のdensity_factor高度区分をISSの実通過高度帯(414.7〜440.8km)に合わせて`0,400,420,430km`に変更。既知の制約として、大気モデルテーブル(NRLMSISE-00)が高度400kmまでしかカバーしておらず、それ以上は最終行の値でクランプされる点をCLAUDE.mdに明記。
- `CLAUDE.md`: `testcase/work_tacode_fortran`の`reference/<case>`・`template/<case>`・`work/<case>`3層構成のケース管理方式を明文化。
- `testcase/work_tacode_fortran/work/work_tacode_iss/src_py/plot_best_vs_reference.py`: `result_PSO/output_global.dat`からObjective最小のベスト解を特定し、そのtacode計算軌道(経過時刻・高度)とリファレンス軌道(GPR平均±標準偏差)を比較プロットするスクリプトを追加(その後`work/work_tacode_iss/`直下から`src_py/`配下に移設)。
- `testcase/work_tacode_fortran/work/work_tacode_iss/src_py/plot_density_profile.py`: ベスト解の大気密度プロファイル(`trajectory.dat`の`density[kg/m3]`列)と、補正なしベースライン・理論値(baseline×density_factor)を高度に対して比較プロットするスクリプトを追加。このスクリプトの作成過程で、下記Fixedの「density_factorが実質無効」バグを発見した。
- `testcase/work_tacode_fortran/template/work_tacode_iss/database/atmospheremodel_baseline/src_py/extend_atmospheremodel.py`: `atmospheremodel.txt`(NRLMSISE-00)を高度400km→460kmまで拡張するスクリプトを追加(`nrlmsise00`パッケージ使用)。
- `testcase/work_tacode_fortran/{template,work}/work_tacode_iss_f107`: `work_tacode_iss`の高度区分density_factor方式に代えて、`work_ninjasat`(`ninja_20240122_20250610`)と同じ「F10.7を直接最適化パラメータとし、NRLMSISE-00で大気密度プロファイルを動的に再計算する」方式のISS版を新規追加。`orbit.ctl`の`Density factor model`を`3`(CTL input)から`1`(Uniform, factor=1.0固定)に変更し、tacode実行前に`$HOME/source/tacode/nrlmsise/NRLMSISE-00/tacode_work/NRLMSISE-00_readctl_2fequal_global.exe`(全球平均NRLMSISE-00, 高度0-700km)を呼んで`atmospheremodel.txt`を都度上書き生成する構成(`run_tacode.sh`)。`borealis.yml`では`name: '# fa10.7'`として`orbit.ctl`末尾の「# Nrlmsise parameres」セクションのF10.7A(bound 100-250)を最適化。referenceは`work_tacode_iss`と同じ`reference/iss_tle`を流用。100×50のPSO本番実行で42ステップ収束、目的関数0.00089・RMS残差0.067km(旧方式と同等)を、F10.7A≈128という単一の物理的パラメータで達成。
- `testcase/work_tacode_fortran/work/work_tacode_iss_f107/src_py/plot_density_profile.py`: F10.7版の大気密度プロファイル比較スクリプトを追加。デフォルトF10.7A(=150)のテーブルをNRLMSISEドライバの単独実行で再生成し、ベストケース自身の`atmospheremodel.txt`・`trajectory.dat`の実測密度と比較する。
- `testcase/work_tacode_fortran/{template,work}/work_tacode_iss_pchip`: `work_tacode_iss`のdensity_factorが実は高度に対する**階段関数**(区分境界で不連続)だったことが判明したため、`scipy.interpolate.PchipInterpolator`(区分3次エルミート補間)で高度制御点間を滑らかに補間する方式のISS版を新規追加。最適化パラメータの構造(高度制御点`0,405,420,435,450km`+係数5個)は`work_tacode_iss`と同一で`borealis.yml`の変更は不要。`orbit.ctl`の`Density factor model`を`1`(Uniform, factor=1.0固定)にし、tacode実行前に新規スクリプト`template/work_tacode_iss_pchip/src_py/apply_pchip_density_factor.py`(`run_tacode.sh`から呼び出し)がPCHIP補間した係数プロファイルをベースラインテーブル(`atmospheremodel_raw.txt`)に掛けて`atmospheremodel.txt`を生成する。100×50のPSO本番実行で57ステップ収束、目的関数0.00095・RMS残差0.071km(旧方式と同等)。専用の`src_py/plot_density_profile.py`で、区分境界でのジャンプが解消され滑らかなプロファイルになっていることを確認。

### Changed
- `src/optimizer_abc/optimizer_abc.py`: `output_global.dat` に、各ステップの時点でのそれまでの最良を書く（以前はそのステップの食料源の中の最良で、偵察蜂が最良の食料源を捨てると悪化した。既知の問題 16）。収束判定は最初の `windowsize_residual` ステップは行わず、分母を初期値の絶対値にした（既知の問題 5）。
- `src/optimizer_pso/optimizer_pso.py`: MPI で粒子を `np.array_split` で均等に分ける（既知の問題 9）。`PSO.maximize` のリストの長さを検査する。
- PSO・ABC: 符号を掛けないアダプタで `maximize: True` を指定すると起動時に止める（以前は黙って最小化を続けた。既知の問題 1）。符号を掛けるアダプタは `flag_apply_sign = True` を宣言する（`shapeoptimizer`・`simple_function`）。
- `src/adapter_shapeoptimizer/`: ジョブの依頼ファイルと外部の監視スクリプトの方式をやめ、外部コードを直接起動して終了を待つ。`num_objectives: 1` なら抗力、`2` なら抗力とモーメントを返す（以前は常に 2 つ返し、単目的で止まった。既知の問題 15）。実行スクリプトの末尾を `wait` にした。
- 外部コードを呼ぶすべてのアダプタ: 起動を `orbital.run_external_code` にまとめた（`cwd` で起動し、子に MPI の環境変数を渡さず、起動前に古い結果ファイルを消し、終了ステータスと結果ファイルを確かめる）。
- `testcase/work_tacode_fortran/reference/iss_tle/src_py/make_reference_iss.py`: 初期速度の算出方法を、測地座標の時系列の有限差分から、SGP4が返すTEME速度をECEF→局所ENU(East/North/Up)へ解析的に変換する方式に変更(`teme_to_ecef_velocity`/`ecef_velocity_to_enu`を追加)。両者の差は±0.01m/s程度で、有限差分も十分高精度だったことを確認済み(比較printも残している)。
- `testcase/work_tacode_fortran/template/work_tacode_iss/orbit.ctl`, `work/work_tacode_iss/borealis.yml`: density_factorの高度区分を`0,400,420,430km`(4点/3区分)から`0,405,420,435,450km`(5点/4閉区間)に変更。理由は下記Fixedを参照。あわせて`parameter_optimized.flag_penalty`を`False`から`True`に変更(密度が実際に効くようになったため、境界外の非物理的な係数を罰則で抑制する)。
- `testcase/work_tacode_fortran/work/{work_tacode_iss,work_tacode_iss_f107}/src_py/plot_density_profile.py`: 出力を1枚の2パネル図(`comparison_density.png`)から、`comparison_density_full.png`(全高度域)・`comparison_density_zoom.png`(ISS高度域ズーム)の2ファイルに分割。

### Fixed
- `src/orbital/orbital.py`: `timeunit: hour` の換算係数が 1436.07 だったのを 3600 に（既知の問題 3）。`directory_path_specify: default` のパスが区切りなしで連結されて存在しない場所になっていたのを直し、誤った語は止めるようにした（既知の問題 26）。`convert_cartesian_geodetic` の分岐を要素ごとにした（既知の問題 14）。
- `src/adapter_tacode/`・`src/adapter_template/adapter_example_externalcode.py`・`src/hidden_adapter_user/`: 時刻（x）の対応点の探索が、基準のデータの範囲の外で配列の末尾へ回り込んでいた。範囲の内側では以前と同じ点を返し、範囲の外の点は比べずに警告する（`orbital.find_bracket_index`。既知の問題 6）。
- PSO・ABC: 目的関数の NaN・無限大が `np.argmin` でリーダーを乗っ取っていた（既知の問題 2）。ABC が 1 要素の配列をスカラーに入れていた、多目的を拒まなかった（既知の問題 12）。
- MPI 実行中の `exit()` で他のランクが止まらなかったのを、`comm.Abort` で全ランクを止めるようにした（既知の問題 8）。
- `src/optimizer_abc/optimizer_abc.py`: onlooker beeフェーズで、担当範囲(`my_indices`)外の食料源を更新した場合に`_sync_all()`のAllreduce(SUM)で更新が消失するバグを修正。`comm.allgather`で各ランクの更新内容を集約し、全プロセスが同一順序で適用する方式に変更。あわせて、onlooker beeのID採番がランク間で不均等な場合に衝突・欠番していた問題も修正。
- `src/borealis.py`: 存在しないモジュールを参照していた`kind_adapter: shapeoptimizer_mp`・`kind_optimizer: PSO_mp`の分岐を削除。`kind_adapter: user`のimport先を実ディレクトリ名`hidden_adapter_user`に修正(いずれも選択すると`ModuleNotFoundError`で即クラッシュしていた)。
- `src/mpi/mpi.py`: `mpitime_measurement_decorated`デコレータが`functools.wraps`未importおよび存在しない`self`参照により機能しない状態だったのを、`orbital.py`の同種デコレータと同じ実装パターンに修正。
- `testcase/work_tacode_fortran/reference/iss_tle/src_py/make_reference_iss.py`: リファレンスのタイムスタンプを暦日(86400秒/日)で生成していたが、`src/orbital/orbital.py`の`timeunit: day`は恒星日(`duration_hour2day=23.9344719177`時間、86164.0989秒)として扱われるため不整合が生じていた。この結果、`adapter_tacode.evaluate_error`内の時刻対応点探索が常に配列先頭(m=0)でマッチし、`self.altitude_opt[m_opt-1]`がPythonの負インデックスで配列末尾にラップアラウンドして実質無意味な比較になっていたにもかかわらず、目的関数はたまたま小さい値(0.05〜0.06)を返し続けていた。タイムスタンプ生成を`orbital.py`と同じ恒星日換算係数に合わせて修正。修正後、`work_tacode_iss`の目的関数は0.0008程度まで低下し、`plot_best_vs_reference.py`での実軌道比較(RMS残差0.06km程度)とも整合するようになった。tacode本体の測地座標変換(`coordinate_system.f90`)・速度合成(`general_function.f90`)側は数値検証の結果バグなしと確認済み。
- `testcase/work_tacode_fortran`(`work_tacode_iss`): `tacode`本体の`atmosphere_variables.f90:set_atmosphere_property`は、問い合わせ高度がベーステーブル(`atmospheremodel_baseline/atmospheremodel.txt`)の範囲外の場合、`density_factor`を掛けずにテーブル最終行の生値をそのまま返す実装になっており、density_factorの乗算はテーブル範囲内で見つけた添字にしか適用されない。元のテーブルは高度0〜400kmしかカバーしておらず、ISSの通過高度(414.7〜440.8km)は常にこの範囲外だったため、`density_factor`が最適化パラメータとして存在するだけでシミュレーション結果に一切影響しない状態だった(`plot_density_profile.py`で発覚。目的関数が良好だったのは軌道当てはめのみによるもので、密度推定は機能していなかった)。tacode本体のソース・バイナリは変更せず、borealis側のデータのみで対処: `atmospheremodel.txt`を460kmまで拡張(`extend_atmospheremodel.py`)。あわせて、density_factorの高度区分自体にも「最後の境界点より上の高度に対応する区分が永久に一致しない(前回値が残留する)」という別のバグがあることが判明したため(`0,180,200,220`のようなN点/N-1区分の設計に共通する構造的な問題)、区分をN+1点/N閉区間になるよう`0,405,420,435,450`に変更してこちらも回避した。修正後、`density[kg/m3]`が高度区分ごとに異なる値を取ることを確認済み(係数1.36/0.55/0.85/1.09)。なお、このケースのリファレンスはSGP4による軌道力学シミュレーションであり実測の大気密度データではないため、得られた係数は「tacodeの軌道力学モデルとSGP4の差」を吸収している側面が強く、そのまま物理的な大気密度の意味を持つとは限らない点に注意。
- `testcase/work_tacode_fortran/template/work_tacode_iss/database/atmospheremodel_baseline/atmospheremodel.txt`: 上記のテーブル拡張作業時、元ファイルの末尾に改行がなかったため、追記した最初の行(401km)が既存の最終行(400km)と1行に結合され、`np.loadtxt`が7列→14列の変化でエラーになる状態になっていた。改行を挿入して修正。同様の追記を行う際は、追記後に必ず読み直して列数を確認すること。

## [0.5.0] - 2024-01-31
### Added
- None

### Changed
- `src/gradient/gradient.py:get_slopelimiter` Primitive variables iterationa are rewritten for efficient computation. 
- `src/meshdata/meshdata.py:` オーバーラップセル判定の高速化

### Fixed
- `src/boundary/boundary.py` Key error in config is fixed.

### Removed
- None
