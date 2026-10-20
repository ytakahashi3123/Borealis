#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown の小さな部分集合を LaTeX の本文に直す（設定ファイルの対応表のため）

  python3 md_to_tex.py config_reference_ja.md config_reference_ja_body.tex

扱うもの
  #（文書の題。本文には出さない）、## / ### / ####（節・小節・小小節）
  パイプの表（longtable にして、ページをまたいで切れる。列は p 列で折り返す）
  箇条書き（- と 1.、2 字下げで入れ子）、段落、```（Verbatim）
  行内の **太字** と `コード`

LaTeX の特殊文字はエスケープする。platex（JIS X 0208）に無い文字は TeX の命令に置き換える。
標準ライブラリだけで動く。
"""
import re
import sys

# platex の JIS X 0208 に無い文字の置き換え（本文とコードの両方）
UNICODE_MAP = {
    '\u00e4': '\\"{a}', '\u00f6': '\\"{o}', '\u00fc': '\\"{u}',
    '\u00c4': '\\"{A}', '\u00d6': '\\"{O}', '\u00dc': '\\"{U}',
    '\u00e9': "\\'{e}", '\u00e8': '\\`{e}',
    '\u2014': '---', '\u2013': '--', '\u00b7': '$\\cdot$',
    '\u00b2': '$^{2}$', '\u00b3': '$^{3}$',
}

TEXT_ESCAPE = {
    '\\': '\\textbackslash{}', '{': '\\{', '}': '\\}', '$': '\\$', '&': '\\&',
    '#': '\\#', '%': '\\%', '_': '\\_', '^': '\\textasciicircum{}',
    '~': '\\textasciitilde{}', '<': '\\textless{}', '>': '\\textgreater{}',
    '|': '\\textbar{}',
}


def escape_text(s):
    out = []
    for c in s:
        if c in TEXT_ESCAPE:
            out.append(TEXT_ESCAPE[c])
        elif c in UNICODE_MAP:
            out.append(UNICODE_MAP[c])
        else:
            out.append(c)
    return ''.join(out)


def escape_code(s):
    """コードの中身。下線・スラッシュ・カンマ・ピリオド・閉じ括弧のあとで改行を許す（狭い表の列で折り返すため）"""
    out = []
    for c in s:
        if c in '<>|':
            out.append(c)          # タイプライタ体には ASCII の字形がある
        elif c in TEXT_ESCAPE:
            out.append(TEXT_ESCAPE[c])
            if c == '_':
                out.append('\\allowbreak{}')
        elif c in UNICODE_MAP:
            out.append(UNICODE_MAP[c])
        else:
            out.append(c)
            if c in '/,.]':
                out.append('\\allowbreak{}')
    return ''.join(out)


def inline(s):
    """行内の書式。先にコードを取り出して置き場所の印にし、残りをエスケープしてから太字を直す"""
    codes = []

    def take_code(m):
        codes.append(m.group(1))
        return '\x00%d\x00' % (len(codes) - 1)

    s = re.sub(r'`([^`]*)`', take_code, s)
    s = escape_text(s)
    s = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', s)
    s = re.sub(r'\x00(\d+)\x00', lambda m: '\\texttt{' + escape_code(codes[int(m.group(1))]) + '}', s)
    return s


def heading_text(s):
    """見出し。PDF のしおりにはコードの書式を外した文字を渡す"""
    tex = inline(s)
    plain = escape_text(s.replace('`', '').replace('**', ''))
    if tex == plain:
        return tex
    return '\\texorpdfstring{%s}{%s}' % (tex, plain)


def display_len(s):
    """表示の幅の見積もり（全角は 2、書式の記号は数えない）"""
    s = s.replace('**', '').replace('`', '')
    return sum(2 if ord(c) > 0x2e7f else 1 for c in s)


def split_row(line):
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|'):
        line = line[:-1]
    # コードの中の | は区切りにしない
    cells, buf, in_code = [], '', False
    for c in line:
        if c == '`':
            in_code = not in_code
        if c == '|' and not in_code:
            cells.append(buf.strip())
            buf = ''
        else:
            buf += c
    cells.append(buf.strip())
    return cells


# よく出る形の表は、列の幅を決め打ちにする（キーの表、開発の状況の表）
FIXED_WIDTHS = {
    ('キー', '選べる値', '既定', '説明・注意'): [0.20, 0.21, 0.18, 0.41],
    ('キー', '既定', '選べる値', '説明・注意'): [0.27, 0.13, 0.18, 0.42],   # Borealis の設定の対応表
    ('機能', '状態', '根拠', '注意'): [0.22, 0.13, 0.35, 0.30],
    ('組', '状態', '根拠', '注意'): [0.22, 0.13, 0.35, 0.30],
}


def column_widths(header, rows):
    """列の幅の割合。中身の長さから見積もり、細すぎる列を作らない"""
    key = tuple(h.replace('`', '') for h in header)
    if key in FIXED_WIDTHS:
        return FIXED_WIDTHS[key]
    ncol = len(header)
    weights = []
    for j in range(ncol):
        lens = [display_len(r[j]) for r in rows if j < len(r)] or [0]
        mean = sum(lens) / len(lens)
        longest = max(lens + [display_len(header[j])])
        weights.append(0.6 * mean + 0.4 * min(longest, 60) + 4.0)
    total = sum(weights)
    frac = [w / total for w in weights]
    floor = 0.10 if ncol <= 4 else 0.06
    frac = [max(f, floor) for f in frac]
    total = sum(frac)
    return [f / total for f in frac]


def table_to_tex(lines):
    header = split_row(lines[0])
    rows = [split_row(l) for l in lines[2:]]
    ncol = len(header)
    rows = [(r + [''] * ncol)[:ncol] for r in rows]
    widths = column_widths(header, rows)
    spec = ''.join('>{\\raggedright\\arraybackslash}p{\\dimexpr %.4f\\linewidth-2\\tabcolsep\\relax}' % (0.995 * w)
                   for w in widths)
    head = ' & '.join('\\textbf{%s}' % inline(h) for h in header) + ' \\\\'
    out = ['\\begingroup\\small',
           '\\begin{longtable}{%s}' % spec,
           '\\toprule', head, '\\midrule', '\\endfirsthead',
           '\\toprule', head, '\\midrule', '\\endhead',
           '\\bottomrule', '\\endlastfoot']
    for r in rows:
        out.append(' & '.join(inline(c) for c in r) + ' \\\\')
    out += ['\\end{longtable}', '\\endgroup', '']
    return out


LIST_RE = re.compile(r'^(\s*)([-*]|\d+\.)\s+(.*)$')


def list_to_tex(lines):
    """箇条書き。字下げ 2 つで 1 段深くなる。字下げされた続きの行は前の項目につなぐ"""
    out = []
    stack = []   # (字下げ, 環境の名前)
    for line in lines:
        m = LIST_RE.match(line)
        if not m:
            out[-1] += ' ' + inline(line.strip())
            continue
        indent = len(m.group(1).expandtabs(4))
        env = 'enumerate' if m.group(2)[0].isdigit() else 'itemize'
        while stack and indent < stack[-1][0]:
            out.append('\\end{%s}' % stack.pop()[1])
        if not stack or indent > stack[-1][0]:
            out.append('\\begin{%s}' % env)
            stack.append((indent, env))
        out.append('\\item ' + inline(m.group(3)))
    while stack:
        out.append('\\end{%s}' % stack.pop()[1])
    out.append('')
    return out


def convert(text):
    lines = text.split('\n')
    out = []
    i = 0
    n = len(lines)
    para = []

    def flush_para():
        if para:
            out.append('\n'.join(inline(p) for p in para))
            out.append('')
            para.clear()

    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith('```'):
            flush_para()
            i += 1
            out.append('\\begin{Verbatim}')
            while i < n and not lines[i].strip().startswith('```'):
                out.append(lines[i])
                i += 1
            out.append('\\end{Verbatim}')
            out.append('')
            i += 1
            continue
        if stripped == '':
            flush_para()
            i += 1
            continue
        m = re.match(r'^(#{1,4})\s+(.*)$', line)
        if m:
            flush_para()
            level = len(m.group(1))
            title = m.group(2).strip()
            if level == 1:
                pass   # 文書の題は外側の .tex が持つ
            else:
                cmd = {2: 'section', 3: 'subsection', 4: 'subsubsection'}[level]
                out.append('\\%s{%s}' % (cmd, heading_text(title)))
                out.append('')
            i += 1
            continue
        if stripped.startswith('|') and i + 1 < n and re.match(r'^\s*\|?\s*:?-{3,}', lines[i + 1]):
            flush_para()
            block = []
            while i < n and lines[i].strip().startswith('|'):
                block.append(lines[i])
                i += 1
            out += table_to_tex(block)
            continue
        if LIST_RE.match(line) and not para:
            block = []
            while i < n and lines[i].strip() != '':
                if not LIST_RE.match(lines[i]) and not lines[i].startswith(' '):
                    break
                block.append(lines[i])
                i += 1
            out += list_to_tex(block)
            continue
        para.append(stripped)
        i += 1
    flush_para()
    return '\n'.join(out) + '\n'


def main():
    if len(sys.argv) != 3:
        sys.stderr.write('usage: md_to_tex.py input.md output.tex\n')
        return 1
    with open(sys.argv[1], encoding='utf-8') as f:
        text = f.read()
    body = convert(text)
    with open(sys.argv[2], 'w', encoding='utf-8') as f:
        f.write('%% このファイルは md_to_tex.py が %s から作る。直接は直さないこと\n' % sys.argv[1])
        f.write(body)
    return 0


if __name__ == '__main__':
    sys.exit(main())
