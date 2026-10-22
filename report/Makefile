# レポートの生成
#   make        : PDF を作る (日英とも)
#   make en     : 英語版だけ
#   make ja     : 日本語版だけ
#   make config : 設定ファイルの対応表 (日本語) を作る
#   make verify : 検証ケース (verification/) を走らせる
#   make figure : 検証ケースの結果と data/ の測定値から図を作り直す
#   make schedule : PSO の重み係数の比べ (data/pso_schedule_*.dat) を作り直す (約 30 秒)
#   make clean  : 中間ファイルを消す (PDF・図・本文は消さない)
#   make distclean : PDF も消す
#
# 本文は .tex が正で、日英の 2 つは同じ構成・同じ数値にそろえる。
# 共通の体裁は borealis.sty にまとめてある (Orthrus の orthrus.sty にならった)。
#
# **エンジンは 2 つある。** 英語版は pdflatex、日本語版は platex + dvipdfmx (jsarticle)。
# どちらもフォントを決め打ちしないので、macOS でも Linux でも同じように組める。
# 目次のために 2 回まわす。
#
# 和文の書体は、埋め込む前にこの機で一度だけ選んでおくこと。選んでいないと、
# PDF に書体の名前だけが載って何も表示されないことがある:
#
#   kanji-config-updmap-user haranoaji        # このユーザーだけ
#   sudo kanji-config-updmap-sys haranoaji    # 機械全体
#
# 確かめるには `pdffonts borealis_report_ja.pdf` で、すべて "emb yes" になっていること。

PYTHON   ?= python3
PDFLATEX ?= pdflatex -interaction=nonstopmode -halt-on-error -file-line-error
PLATEX   ?= platex -interaction=nonstopmode -halt-on-error -file-line-error
DVIPDF   ?= dvipdfmx -V 7

.PHONY: all en ja config verify figure schedule clean distclean

all: en ja config

en: borealis_report_en.pdf
ja: borealis_report_ja.pdf
config: borealis_config_ja.pdf

borealis_report_en.pdf: borealis_report_en.tex borealis.sty
	$(PDFLATEX) $<
	$(PDFLATEX) $<

borealis_report_ja.pdf: borealis_report_ja.tex borealis.sty
	$(PLATEX) $<
	$(PLATEX) $<
	$(DVIPDF) $(basename $<)

# 設定ファイルの対応表 (日本語)。本文の正は config_reference_ja.md で、
# md_to_tex.py が LaTeX の本文 config_reference_ja_body.tex に直す
config_reference_ja_body.tex: config_reference_ja.md md_to_tex.py
	$(PYTHON) md_to_tex.py $< $@

borealis_config_ja.pdf: borealis_config_ja.tex config_reference_ja_body.tex borealis.sty
	$(PLATEX) $<
	$(PLATEX) $<
	$(DVIPDF) $(basename $<)

verify:
	$(PYTHON) run_verification.py

figure:
	$(PYTHON) make_figures.py

schedule:
	$(PYTHON) run_pso_schedule.py

clean:
	rm -f *.aux *.log *.out *.toc *.dvi *.fls *.fdb_latexmk *.xdv *.synctex.gz

distclean: clean
	rm -f borealis_report_en.pdf borealis_report_ja.pdf borealis_config_ja.pdf
