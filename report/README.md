# report/

Borealis の詳細なレポート。`../README.md` より踏み込んで、問題の設定・コードの構成・最適化の手法・
並列化・検証を書いてある。検証の節は、解析解の分かっている問題との比較を図と表で示す。
体裁と作り方は Orthrus のレポート（`~/source/orthrus/orthrus-dev/report/`）にならった。

| ファイル | 中身 |
|---|---|
| `borealis_report_en.tex` / `.pdf` | 本文（英語） |
| `borealis_report_ja.tex` / `.pdf` | 本文（日本語） |
| `borealis_config_ja.pdf`（`config_reference_ja.md`） | 設定ファイル `borealis.yml` のキーの一覧（日本語） |
| `borealis.sty` | 日英で共通の体裁（ページ、フォント、表、表題） |
| `md_to_tex.py` | `config_reference_ja.md` を LaTeX の本文に直す |
| `verification/<ケース>/borealis.yml` | 検証ケース（5 次元のずらした球関数。PSO・GA の単目的と 2 目的、ABC、ベイズ最適化） |
| `run_verification.py` | 検証ケースを、numpy の乱数の種を固定して走らせる |
| `data/parallel_*.dat` | 並列評価の測定（2026-10-19、開発機）。ケースごとの開始・終了の時刻とコアの固定 |
| `figure/*.png` | 図。`make_figures.py` が作る |
| `make_figures.py` | 検証ケースの結果と `data/` から図を作り直す |
| `Makefile` | `make verify` で検証、`make figure` で図、`make` で PDF |

## 作り直し方

```
cd report
make verify        # 検証ケースを走らせる（数秒。乱数の種を固定するので毎回同じ答えになる）
make figure        # 図を作り直す
make               # PDF を作る（日英と設定の一覧）
make en            # 英語版だけ
make ja            # 日本語版だけ
make config        # 設定の一覧だけ
```

検証ケースが書き出す `verification/*/result_*/` と `log_borealis` は生成物である。

**`data/parallel_*.dat` は自動では作り直さない。** 並列評価の測定は、ダミーの MPI のプログラムと
SU2 + preCICE を実際に走らせた記録で、作り方はリポジトリの外の開発の記録にある。
図を作り直しても、この 2 つのタイムラインは変わらない。

**エンジンは 2 つある。** 英語版は `pdflatex`、日本語版と設定の一覧は `platex` + `dvipdfmx`（jsarticle）で
組む。目次のためにどちらも 2 回まわす。**フォントは決め打ちしていない**ので、
macOS でも Linux でも同じように組める。和文は jsarticle に任せてある
（本文は明朝、見出しはゴシック）。

**和文の書体は、埋め込む前に一度だけ選んでおくこと。** 選んでいないと、PDF に書体の
名前だけが載って何も表示されないことがある。

```bash
kanji-config-updmap-user haranoaji        # このユーザーだけ
sudo kanji-config-updmap-sys haranoaji    # 機械全体
```

確かめるには `pdffonts borealis_report_ja.pdf` で、すべて "emb yes" になっていること。

## 本文と図を直すとき

- **本文は `.tex` が正**。PDF は生成物だが、読む人が増えるので一緒に置いてある
- **設定の一覧は `config_reference_ja.md` が正**。`config_reference_ja_body.tex` は `md_to_tex.py` が作る
- 日英の 2 つは同じ構成・同じ数値にそろえること。片方だけ直すと食い違う
- 手法の式は、文献の一般の形でなく**ソースに書いてあるとおりの形**で書く。コードを変えたら式も直す
- 図の軸ラベルは慣例どおり英語にしてある（日本語版でも同じ図を使う）
- ISS の適用例の数値は 2026 年 8 月の実行の記録（`CHANGELOG.md`）から引いたもので、自動では作り直さない
