#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
toms2xml.py — The ONE 智能钢琴 .toms ⇄ MusicXML 双向转换器（拖拽即用）
======================================================================
用法（任选其一）：
  [方式A · 零依赖] 把文件直接拖到本脚本图标上（可一次拖多个），自动按扩展名转换：
                    .toms        → score.xml（解密还原五线谱）
                    .xml/.musicxml/.mxl → score.toms（打包回 App 可读格式，MXL 自动解包）
  [方式B · 命令行] python toms2xml.py 文件1 [文件2 ...] [--out 输出路径]
  [方式C · 拖拽窗口] 双击运行，弹出窗口：
                    - 拖入文件转换
                    - 可填输出路径（本地目录 或 ftp://192.168.3.7:2122/手机路径），
                      转换后的 score.toms + hash_sums 直接输出/上传到该处

导出命名固定（与原版配套一致）：
  乐谱导出固定为 score.toms / score.xml，校验清单固定为 hash_sums。

格式链（来自 APK 逆向 libsmartpiano-player.so）：
  .toms = RC4(key, 预热1024步) → zlib(deflate) → MusicXML 3.0
  key = 85 31 f8 3c 0a 1f ac 2b 04 bd fd b2 cb b3 1a 85  (.data 0x30e158)
  RC4 为对称算法，加密与解密同一函数。

兼容性处理（让打包结果能被 App 正常打开）：
  1) 完整 zlib 流压缩（level 6）：自动生成 78 9C 头 + Adler-32 校验，
     与原版 miniz 压缩完全同构（App 的 mz_uncompress 会校验 Adler-32）
  2) 内容原样打包：App 支持 2 part / 多 tempo / appearance 等完整 MusicXML 3.0 内容，
     只有 4.0 版本头需要降级为 3.0（DOCTYPE / version / standalone）
  3) hash_sums 与 score.toms 自动配对（MD5 精确一致）
"""
import ftplib
import hashlib
import io
import os
import re
import sys
import zipfile
import zlib
import xml.etree.ElementTree as ET

RC4_KEY = bytes.fromhex('85 31 f8 3c 0a 1f ac 2b 04 bd fd b2 cb b3 1a 85')
WARMUP = 0x400          # 1024 步预热（rc4_crypt 第4参数 w3）
HASH_SUMS_NAME = 'hash_sums'
FIXED_BASE = 'score'    # 导出固定基础名
ZLIB_HEAD = b'\x78\x9c' # 与原版 miniz 一致的 zlib 头（FLG=0x9c）
MUSICXML_HEADER = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\r\n'
                   '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.0 Partwise//EN" '
                   '"http://www.musicxml.org/dtds/partwise.dtd">\r\n')

# 标准头部模板（取自 App 原版谱 Finale 风格，已验证 App 100% 兼容）。
# 关键：MuseScore 4 导出的头部（Leland 字体/miscellaneous-field/print-object part-name 等）
# 会让 App 解析失败打不开 —— 统一替换成该模板即可（音符内容完全不动）。
STANDARD_HEAD = '''<?xml version="1.0" encoding="UTF-8" standalone="no"?>

<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">

<score-partwise version="3.0">

  <movement-title>{TITLE}</movement-title>

  <identification>

    <creator type="composer">自制</creator>

    <encoding>

      <software>toms2xml</software>

      <encoding-date>2026-09-30</encoding-date>

    </encoding>

  </identification>

  <defaults>

    <scaling>

      <millimeters>7.2319</millimeters>

      <tenths>40</tenths>

    </scaling>

    <page-layout>

      <page-height>1643</page-height>

      <page-width>1161</page-width>

      <page-margins type="both">

        <left-margin>105</left-margin>

        <right-margin>70</right-margin>

        <top-margin>70</top-margin>

        <bottom-margin>70</bottom-margin>

      </page-margins>

    </page-layout>

    <system-layout>

      <system-margins>

        <left-margin>0</left-margin>

        <right-margin>0</right-margin>

      </system-margins>

      <system-distance>121</system-distance>

      <top-system-distance>70</top-system-distance>

    </system-layout>

    <staff-layout>

      <staff-distance>80</staff-distance>

    </staff-layout>

    <appearance>

      <line-width type="stem">0.7487</line-width>

      <line-width type="beam">5</line-width>

      <line-width type="staff">0.7487</line-width>

      <line-width type="light barline">0.7487</line-width>

      <line-width type="heavy barline">5</line-width>

      <line-width type="leger">0.7487</line-width>

      <line-width type="ending">0.7487</line-width>

      <line-width type="wedge">0.7487</line-width>

      <line-width type="enclosure">0.7487</line-width>

      <line-width type="tuplet bracket">0.7487</line-width>

      <note-size type="grace">60</note-size>

      <note-size type="cue">60</note-size>

      <distance type="hyphen">120</distance>

      <distance type="beam">8</distance>

    </appearance>

    <music-font font-family="Maestro,engraved" font-size="20.5"/>

    <word-font font-family="Times New Roman" font-size="10.25"/>

  </defaults>

  <part-list>

    <score-part id="P1">

      <part-name>Piano</part-name>

      <part-abbreviation>Pno.</part-abbreviation>

      <score-instrument id="P1-I1">

        <instrument-name>Acoustic Grand Piano</instrument-name>

        <instrument-sound>keyboard.piano</instrument-sound>

      </score-instrument>

      <midi-instrument id="P1-I1">

        <midi-channel>1</midi-channel>

        <midi-program>1</midi-program>

        <volume>80</volume>

        <pan>0</pan>

      </midi-instrument>

    </score-part>

  </part-list>
'''


def standardize_head(xml_bytes: bytes) -> bytes:
    """把 MusicXML 头部（到 <part 之前）统一替换为 STANDARD_HEAD。
    保留源谱的 movement-title；音符/小节/排版内容一律不动。
    修复 MuseScore 4 等导出头部不被 App 识别导致打不开的问题。"""
    s = xml_bytes.decode('utf-8')
    m = re.search(r'<movement-title>([^<]*)</movement-title>', s)
    title = m.group(1).strip() if m else '我的曲谱'
    head = STANDARD_HEAD.format(TITLE=title)
    pos = s.find('<part ')
    if pos < 0:
        return xml_bytes
    return (head + s[pos:]).encode('utf-8')


# ---------------- 基础算法（与 App 完全一致） ----------------
def md5_of(path: str) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def rc4_crypt(data: bytes, key: bytes = RC4_KEY, warmup: int = WARMUP) -> bytes:
    """与 libsmartpiano-player.so rc4_setup/rc4_crypt 等价的魔改 RC4（加解密同函数）"""
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) & 0xff
        S[i], S[j] = S[j], S[i]
    i = j = 0
    for _ in range(warmup):
        i = (i + 1) & 0xff
        j = (j + S[i]) & 0xff
        S[i], S[j] = S[j], S[i]
    out = bytearray(len(data))
    for k in range(len(data)):
        i = (i + 1) & 0xff
        j = (j + S[i]) & 0xff
        S[i], S[j] = S[j], S[i]
        out[k] = data[k] ^ S[(S[i] + S[j]) & 0xff]
    return bytes(out)


def toms_to_xml(toms_bytes: bytes) -> bytes:
    """.toms 字节 -> 明文 MusicXML 字节；失败抛异常"""
    rc = rc4_crypt(toms_bytes)
    try:
        xml = zlib.decompressobj(15).decompress(rc)
    except zlib.error as e:
        raise ValueError(f'解密后无法 zlib 解压（{e}），不是本 App 的 .toms 格式')
    if not xml.lstrip().startswith(b'<?xml'):
        raise ValueError('解密后不是 XML，文件可能来自其他版本')
    return xml


# ---------------- XML 兼容化（多 part 合并 + 4.0 降级） ----------------
def _split_notes(mbody):
    """小节体内音符列表 [(note块, 是否chord)]"""
    return [(m.group(0), '<chord/>' in m.group(0)) for m in re.finditer(r'<note\b[^>]*>.*?</note>', mbody, re.S)]


def _note_dur(nb):
    m = re.search(r'<duration>(\d+)</duration>', nb)
    return int(m.group(1)) if m else 0


def _set_voice(block, v):
    return re.sub(r'(<voice>)\d+(</voice>)', lambda m: m.group(1) + str(v) + m.group(2), block, count=1)


def _add_staff_end(block, staff_no):
    """<staff>N</staff> 插到 </note> 前（MusicXML DTD 顺序：stem/notehead 之后）"""
    return re.sub(r'\s*(</note>)', '\n        <staff>%d</staff>\n      \\1' % staff_no, block, count=1)


def _parse_measures(part_body):
    out = {}
    for m in re.finditer(r'<measure\b([^>]*)>(.*?)</measure>', part_body, re.S):
        attrs = m.group(1)
        num = re.search(r'number="([^"]+)"', attrs)
        out[num.group(1) if num else str(len(out) + 1)] = (attrs, m.group(2))
    return out


def _dual_clef_attrs(att):
    """把单谱表 attributes 转为双谱表（staves=2 + 高低音谱号）；无 attributes 返回 ''"""
    if not att:
        return ''
    att = re.sub(r'\s*<staves>\d+</staves>', '', att)
    att = re.sub(r'\s*<clef\b.*?</clef>', '', att, flags=re.S)
    return att.replace('</attributes>',
        '<staves>2</staves>\n        <clef number="1"><sign>G</sign><line>2</line></clef>\n'
        '        <clef number="2"><sign>F</sign><line>4</line></clef>\n      </attributes>')


def merge_parts(xml_bytes: bytes):
    """多 part -> 1 part(Piano, staves=N)（App 兼容形态，已验证可打开）。

    要点（多次实测锁定）：
      * 忠实保留源文件排版：measure 的 print(new-system)/width、note 的 default-x、
        direction/sound(速度) 等全部原样保留 —— App 按这些信息分行显示；
      * 只做 2 part → 1 part 双谱表合并：右手音符标 staff=1、左手标 staff=2，
        backup 对齐时值；<staff> 放 note 末尾（DTD 顺序）；
      * 头部（identification/defaults/credit 等）保留源文件自己的，不重建。

    返回 (字节, 处理说明)。已是单 part 则原样返回。"""
    s = xml_bytes.decode('utf-8')
    parts = re.findall(r'<part id="([^"]+)"\s*>(.*?)</part>', s, re.S)
    if len(parts) <= 1:
        return xml_bytes, ''
    n = len(parts)
    head = s[:s.find('<part ')]

    # part-list：只留第一个（Piano），删 part-group
    new_pl = ('  <part-list>\n    <score-part id="P1">\n      <part-name>Piano</part-name>\n'
              '      <part-abbreviation>Pno.</part-abbreviation>\n      <score-instrument id="P1-I1">\n'
              '        <instrument-name>Acoustic Grand Piano</instrument-name>\n'
              '        <instrument-sound>keyboard.piano</instrument-sound>\n      </score-instrument>\n'
              '      <midi-instrument id="P1-I1">\n        <midi-channel>1</midi-channel>\n'
              '        <midi-program>1</midi-program>\n      </midi-instrument>\n    </score-part>\n  </part-list>\n\n')
    head = re.sub(r'\s*<part-list>.*?</part-list>', '\n' + new_pl, head, flags=re.S)
    head = re.sub(r'\s*<part-group\b.*?</part-group>', '', head, flags=re.S)

    pms = [_parse_measures(b) for _, b in parts]
    nums = sorted(set().union(*[set(p.keys()) for p in pms]), key=lambda x: int(x) if x.isdigit() else 0)

    # 各 part 的 divisions（从各自第一个小节的 attributes 提取；默认同 P1）
    part_divs = []
    for pm in pms:
        first_att = ''
        for k in sorted(pm.keys(), key=lambda x: int(x) if x.isdigit() else 0):
            m = re.search(r'<attributes>.*?</attributes>', pm[k][1], re.S)
            if m:
                first_att = m.group(0)
                break
        d = re.search(r'<divisions>(\d+)</divisions>', first_att)
        part_divs.append(int(d.group(1)) if d else None)
    p1_div = part_divs[0] or 12

    merged = []
    for num in nums:
        attrs1, b1 = pms[0].get(num, ('', ''))
        # attributes：P1 的，转双谱表
        att = _dual_clef_attrs(re.search(r'<attributes>.*?</attributes>', b1, re.S).group(0) if re.search(r'<attributes>.*?</attributes>', b1, re.S) else '')
        # 非 note/attributes 元素（print/direction/sound 等）原样保留
        rest1 = re.sub(r'<note\b[^>]*>.*?</note>', '', b1, flags=re.S)
        rest1 = re.sub(r'<attributes>.*?</attributes>', '', rest1, flags=re.S)
        # 各 part 音符合并：P1 notes + backup(复位) + P2..N notes（backup 必须在 P1 后 P2 前）
        # 注意：不同 part 的 divisions 可能不同（Finale 导出常见：P1=12、P2=4），
        # 必须把 P2..N 的 duration 归一化到 P1 的 divisions，否则 App 按同一 divisions 解析时值全错。
        n1_blocks = [_add_staff_end(_set_voice(nb, 1), 1) for nb, _ in _split_notes(b1)]
        other_blocks = []
        for pi in range(1, n):
            b = pms[pi].get(num, ('', ''))[1]
            pdiv = part_divs[pi] or p1_div
            scale = p1_div / pdiv if pdiv else 1.0
            for nb, ch in _split_notes(b):
                if ch:
                    continue
                if scale != 1.0:
                    def _scl(mm):
                        v = int(float(mm.group(1)) * scale)
                        return f'<duration>{v}</duration>'
                    nb = re.sub(r'<duration>(\d+)</duration>', _scl, nb)
                other_blocks.append(_add_staff_end(_set_voice(nb, 1), pi + 1))
        # backup：P1 小节总时值（chord 不计）
        total = sum(_note_dur(nb) for nb, ch in _split_notes(b1) if not ch)
        backup = f'<backup>\n        <duration>{total}</duration>\n      </backup>' if total and n > 1 else ''
        body = f'{att}\n        {rest1}{"".join(n1_blocks)}\n        {backup}\n        {"".join(other_blocks)}'
        merged.append(f'<measure {attrs1.strip()}>' if attrs1.strip() else f'<measure number="{num}">')
        merged[-1] = merged[-1] + f'\n      {body}\n    </measure>'

    xs = head + '  <part id="P1">\n    ' + '\n    '.join(merged) + '\n  </part>\n</score-partwise>\n'
    note = f'已将 {n} 个 part 合并为单 part {n} 谱表（保留原排版）'
    if n > 2:
        note += '（⚠ 多乐器谱超出 App 常规支持，建议在 MuseScore 中合并为钢琴谱再导出）'
    return xs.encode('utf-8'), note


def downgrade_musicxml40(xml_bytes: bytes):
    """MusicXML 4.0 → 3.0 最小降级：只改版本头，不动任何内容元素。
    经验证（Untitled1 等）：App 支持 2 part、多 tempo、appearance 等完整 3.0 内容，
    唯一要求是 3.0 版本头；内容必须原样保留。返回 (字节, 是否降级)"""
    s = xml_bytes.decode('utf-8')
    changed = False
    if 'MusicXML 4.0' in s:
        s = s.replace('MusicXML 4.0 Partwise', 'MusicXML 3.0 Partwise')
        changed = True
    if 'version="4.0"' in s:
        s = s.replace('<score-partwise version="4.0">', '<score-partwise version="3.0">')
        changed = True
    if 'standalone=' not in s[:80]:
        s = re.sub(r'(<\?xml[^>]*?encoding="UTF-8"[^>]*?)(\?>)', r'\1 standalone="no"\2', s, count=1)
        changed = True
    return s.encode('utf-8'), changed


def fix_low_notes(xml_bytes) -> bytes:
    """App 只接受 octave >= 1 的音符（原版 42 首最低 octave 1）。
    octave 0（A0/G0/E0 等）会让 App 解析崩溃打不开；统一升 8 度(octave 0->1)。
    注意：必须精确匹配 <octave>0</octave>，不能误伤 display-octave。"""
    if isinstance(xml_bytes, bytes):
        xml_bytes = xml_bytes.decode('utf-8')
    out = re.sub(r'<octave>0</octave>', '<octave>1</octave>', xml_bytes)
    return out.encode('utf-8')


def xml_to_toms(xml_bytes: bytes):
    """明文 MusicXML -> (toms字节, 处理说明)；失败抛异常。
    原则：内容原样打包（App 支持 2 part / 多 tempo / appearance 等完整 3.0 内容），
    只做 4.0→3.0 版本头降级，绝不动音符、声部、速度等任何内容。"""
    if xml_bytes[:3] == b'\xef\xbb\xbf':
        xml_bytes = xml_bytes[3:]
    if not xml_bytes.lstrip().startswith(b'<?xml'):
        raise ValueError('不是 XML 文档（开头应为 <?xml）')
    xml_bytes = standardize_head(xml_bytes)
    xml_bytes, downgraded = downgrade_musicxml40(xml_bytes)
    xml_bytes = fix_low_notes(xml_bytes)
    # 完整 zlib 流：compressobj(6) 自动生成 78 9C 头（FLEVEL=2，与原版 miniz level 6 一致）+ Adler-32 校验尾
    # 注意：绝不能用手工 78 9C + raw deflate（缺 Adler-32，App 的 mz_uncompress 校验失败会拒绝）
    co = zlib.compressobj(6, zlib.DEFLATED)
    deflated = co.compress(xml_bytes) + co.flush()
    notes = []
    if downgraded:
        notes.append('已自动降级为 MusicXML 3.0')
    return rc4_crypt(deflated), '；'.join(notes)


def read_mxl(mxl_bytes: bytes) -> bytes:
    """MXL（压缩 MusicXML）-> 明文 MusicXML 字节"""
    try:
        z = zipfile.ZipFile(io.BytesIO(mxl_bytes))
    except zipfile.BadZipFile as e:
        raise ValueError(f'不是有效的 MXL/ZIP 包: {e}')
    names = z.namelist()
    # 标准 MXL：META-INF/container.xml 指明根文件
    if 'META-INF/container.xml' in names:
        c = z.read('META-INF/container.xml').decode('utf-8', 'replace')
        m = re.search(r'full-path="([^"]+)"', c)
        if m and m.group(1) in names:
            return z.read(m.group(1))
    # 兜底：包里任意 .xml/.musicxml
    for n in names:
        if n.lower().endswith(('.musicxml', '.xml')):
            return z.read(n)
    raise ValueError('MXL 包内未找到 MusicXML 文件')


# ---------------- 输出路径（本地目录 / FTP） ----------------
def parse_out_spec(s):
    """解析输出路径：None / ('local', 目录) / ('ftp', {host,port,user,pw,path})"""
    s = (s or '').strip()
    if not s:
        return None
    if s.lower().startswith('ftp://'):
        rest = s[6:]
        auth, _, hostport_path = (rest.rpartition('@') if '@' in rest else ('', '', rest))
        user, _, pw = auth.partition(':')
        hp, _, path = hostport_path.partition('/')
        if ':' in hp:
            host, port = hp.rsplit(':', 1)
            port = int(port)
        else:
            host, port = hp, 21
        return ('ftp', {'host': host, 'port': port,
                        'user': user or 'anonymous', 'pw': pw,
                        'path': '/' + path})
    return ('local', s)


def save_to(out_spec, filename, data):
    """按输出路径写出文件；返回展示用的位置描述"""
    if out_spec is None:
        raise ValueError('未指定输出路径')
    if out_spec[0] == 'ftp':
        spec = out_spec[1]
        ftp = ftplib.FTP()
        ftp.connect(spec['host'], spec['port'], timeout=15)
        ftp.login(spec['user'], spec['pw'])
        ftp.storbinary('STOR ' + spec['path'].rstrip('/') + '/' + filename, io.BytesIO(data))
        try:
            ftp.quit()
        except Exception:
            pass
        return f'ftp://{spec["host"]}:{spec["port"]}{spec["path"].rstrip("/")}/{filename}'
    p = os.path.join(out_spec[1], filename)
    with open(p, 'wb') as f:
        f.write(data)
    return p


def build_hash_sums(toms_bytes: bytes) -> bytes:
    return (hashlib.md5(toms_bytes).hexdigest() + '  ' + FIXED_BASE + '.toms\n').encode('utf-8')


def check_source_hash(toms_path: str):
    """转换前验证源 .toms 与同目录 hash_sums 一致性；返回提示"""
    dirpath = os.path.dirname(os.path.abspath(toms_path))
    name = os.path.basename(toms_path)
    hp = os.path.join(dirpath, HASH_SUMS_NAME)
    if not os.path.isfile(hp):
        return '（同目录无 hash_sums，跳过源校验）'
    cur = md5_of(toms_path)
    try:
        with open(hp, 'r', encoding='utf-8') as f:
            text = f.read()
        m = re.search(r'^([0-9a-fA-F]{32})\s+' + re.escape(name) + r'\s*$', text, re.M)
        if m and m.group(1).lower() == cur:
            return 'hash_sums 源校验一致 ✓'
        return f'⚠ hash_sums 记录值与实测不一致（记录 {m.group(1) if m else "无"}，实测 {cur}）'
    except Exception as e:
        return f'⚠ hash_sums 读取失败: {e}'


# ---------------- 核心转换 ----------------
def convert(path: str, out_spec=None) -> str:
    """转换单个文件；返回结果文本"""
    base = os.path.basename(path)
    if not os.path.isfile(path):
        return f'✗ {base}: 文件不存在'
    ext = os.path.splitext(base)[1].lower()
    try:
        with open(path, 'rb') as f:
            raw = f.read()
    except Exception as e:
        return f'✗ {base}: 读取失败 - {e}'

    # ---- .toms → score.xml（解密） ----
    if ext == '.toms':
        hash_note = check_source_hash(path)
        try:
            xml = toms_to_xml(raw)
        except Exception as e:
            return f'✗ {base}: 转换失败 - {e}'
        dest = out_spec or ('local', os.path.dirname(os.path.abspath(path)))
        try:
            loc = save_to(dest, FIXED_BASE + '.xml', xml)
        except Exception as e:
            return f'✗ {base}: 输出失败 - {e}'
        title = ''
        m = re.search(rb'<movement-title>([^<]+)</movement-title>', xml[:8000])
        if m:
            title = m.group(1).decode('utf-8', 'replace')
        note = f'《{title}》' if title else ''
        return (f'✓ {base} -> {FIXED_BASE}.xml\n'
                f'    {len(xml):,} 字节 XML  {note}\n'
                f'    输出: {loc}\n'
                f'    {hash_note}')

    # ---- .xml / .musicxml / .mxl → score.toms + hash_sums ----
    if ext in ('.xml', '.musicxml', '.mxl'):
        src_label = 'MXL 包' if ext == '.mxl' else 'XML'
        try:
            xml_src = read_mxl(raw) if ext == '.mxl' else raw
            xml_src, merge_note = merge_parts(xml_src)
            toms, notes = xml_to_toms(xml_src)
            if merge_note:
                notes = (notes + '；' + merge_note) if notes else merge_note
        except Exception as e:
            return f'✗ {base}: 转换失败 - {e}'
        dest = out_spec or ('local', os.path.dirname(os.path.abspath(path)))
        try:
            loc1 = save_to(dest, FIXED_BASE + '.toms', toms)
            loc2 = save_to(dest, HASH_SUMS_NAME, build_hash_sums(toms))
        except Exception as e:
            return f'✗ {base}: 输出失败 - {e}'
        title = ''
        m = re.search(rb'<movement-title>([^<]+)</movement-title>', xml_src[:8000])
        if m:
            title = m.group(1).decode('utf-8', 'replace')
        note = f'《{title}》' if title else ''
        hd = '；'.join([x for x in [notes, f'{len(toms):,}B'] if x])
        return (f'✓ {base}({src_label}) -> {FIXED_BASE}.toms + {HASH_SUMS_NAME}\n'
                f'    {hd}  {note}\n'
                f'    {loc1}\n'
                f'    {loc2}')

    return f'✗ {base}: 仅支持 .toms / .xml / .musicxml / .mxl，已跳过'


# ---------------- FTP 目录浏览器（手机路径选择） ----------------
class FtpBrowser:
    """连接 FTP、列出并导航目录，选定后把 ftp:// 地址回填到输出路径输入框。
    背景：Windows 文件夹选择框不支持 FTP，故内置浏览器。"""

    def __init__(self, root, on_select):
        import tkinter as tk
        self.tk = tk
        self.on_select = on_select
        self.ftp = None
        self.conn_info = None   # dict(host, port, user, pw)
        self.path = '/'

        self.top = tk.Toplevel(root)
        self.top.title('选择手机 FTP 目录')
        self.top.geometry('640x420')
        self.top.configure(bg='#f5f6fa')

        # 连接参数行
        row0 = tk.Frame(self.top, bg='#f5f6fa')
        row0.pack(fill='x', padx=12, pady=(10, 4))
        tk.Label(row0, text='FTP 地址', bg='#f5f6fa', font=('Microsoft YaHei UI', 9)).pack(side='left')
        self.e_host = tk.Entry(row0, width=22, font=('Consolas', 9))
        self.e_host.insert(0, '192.168.3.7:2122')
        self.e_host.pack(side='left', padx=(4, 10))
        tk.Label(row0, text='用户', bg='#f5f6fa', font=('Microsoft YaHei UI', 9)).pack(side='left')
        self.e_user = tk.Entry(row0, width=8, font=('Consolas', 9))
        self.e_user.pack(side='left', padx=(4, 10))
        tk.Label(row0, text='密码', bg='#f5f6fa', font=('Microsoft YaHei UI', 9)).pack(side='left')
        self.e_pw = tk.Entry(row0, width=10, show='*', font=('Consolas', 9))
        self.e_pw.pack(side='left', padx=(4, 10))
        tk.Button(row0, text='连接', command=self.connect, bg='#4a7dff', fg='white',
                  relief='flat', font=('Microsoft YaHei UI', 9)).pack(side='left')

        # 路径栏（可编辑：支持粘贴 /sdcard/... 或完整 ftp://... 后回车跳转）
        self.e_path = tk.Entry(self.top, font=('Consolas', 10), bg='white', fg='#222',
                               relief='solid', bd=1)
        self.e_path.insert(0, '/')
        self.e_path.pack(fill='x', padx=12, pady=4)
        self.e_path.bind('<Return>', lambda e: self.jump())
        tk.Label(self.top, text='路径可直接粘贴（如 /sdcard/Android/data/com.theonepiano.smartpiano/files/score 或 ftp://...），回车跳转',
                 bg='#f5f6fa', fg='#888', font=('Microsoft YaHei UI', 9)).pack(anchor='w', padx=12)

        # 目录列表
        frame = tk.Frame(self.top, bg='#f5f6fa')
        frame.pack(fill='both', expand=True, padx=12, pady=4)
        sb = tk.Scrollbar(frame)
        sb.pack(side='right', fill='y')
        self.listbox = tk.Listbox(frame, yscrollcommand=sb.set, font=('Consolas', 10),
                                  relief='solid', bd=1, selectbackground='#4a7dff')
        self.listbox.pack(fill='both', expand=True)
        sb.config(command=self.listbox.yview)
        self.listbox.bind('<Double-Button-1>', lambda e: self.enter_dir())

        # 按钮行
        row2 = tk.Frame(self.top, bg='#f5f6fa')
        row2.pack(fill='x', padx=12, pady=(4, 10))
        tk.Button(row2, text='↑ 上级目录', command=self.go_up, bg='#e8ecf2', relief='flat',
                  font=('Microsoft YaHei UI', 9)).pack(side='left')
        tk.Button(row2, text='刷新', command=self.refresh, bg='#e8ecf2', relief='flat',
                  font=('Microsoft YaHei UI', 9)).pack(side='left', padx=8)
        tk.Button(row2, text='取消', command=self.top.destroy, bg='#e8ecf2', relief='flat',
                  font=('Microsoft YaHei UI', 9)).pack(side='right')
        tk.Button(row2, text='选择此目录', command=self.pick, bg='#0a7d32', fg='white',
                  relief='flat', font=('Microsoft YaHei UI', 10)).pack(side='right', padx=8)

    def _norm(self, p):
        """该 FTP 服务器 pwd 可能返回相对格式，统一为 /a/b 规范路径"""
        if not p:
            return '/'
        if not p.startswith('/'):
            p = '/' + p
        if p != '/' and p.endswith('/'):
            p = p.rstrip('/')
        return p

    def connect(self):
        import ftplib
        hp = self.e_host.get().strip()
        if ':' in hp:
            host, port = hp.rsplit(':', 1)
            try: port = int(port)
            except ValueError: port = 21
        else:
            host, port = hp, 21
        user = self.e_user.get().strip() or 'anonymous'
        pw = self.e_pw.get()
        try:
            ftp = ftplib.FTP()
            ftp.connect(host, port, timeout=10)
            ftp.login(user, pw)
        except Exception as e:
            self.listbox.delete(0, 'end')
            self.listbox.insert('end', f'✗ 连接失败: {e}')
            return
        if self.ftp is not None:
            try: self.ftp.quit()
            except Exception: pass
        self.ftp = ftp
        self.conn_info = {'host': host, 'port': port, 'user': user, 'pw': pw}
        self.path = '/'
        try:
            self.path = self._norm(self.ftp.pwd() or '/')
        except Exception:
            pass
        self.refresh()

    def refresh(self):
        self.listbox.delete(0, 'end')
        if self.ftp is None:
            return
        try:
            lines = []
            self.ftp.retrlines('LIST', lines.append)  # 无参数=列出当前目录（该服务器不支持 LIST 带绝对路径）
        except Exception as e:
            self.listbox.insert('end', f'✗ 列表失败: {e}')
            return
        dirs, files = [], []
        for ln in lines:
            parts = ln.split(None, 8)
            if len(parts) < 9:
                continue
            name = parts[8]
            if name in ('.', '..'):
                continue
            (dirs if ln.startswith('d') else files).append(name)
        dirs.sort(); files.sort()
        for d in dirs:
            self.listbox.insert('end', '[目录] ' + d)
        for f in files:
            self.listbox.insert('end', '       ' + f)
        self.e_path.delete(0, 'end')
        self.e_path.insert(0, self.path)

    def jump(self):
        """粘贴路径跳转：支持 /绝对路径、相对路径、完整 ftp://host:port/path"""
        if self.ftp is None:
            return
        raw = self.e_path.get().strip()
        if not raw:
            return
        if raw.lower().startswith('ftp://'):
            rest = raw[6:]
            _, _, path = rest.partition('/')
            raw = '/' + path
        try:
            self.ftp.cwd(raw)
            self.path = self._norm(self.ftp.pwd() or raw)
        except Exception as e:
            self.listbox.delete(0, 'end')
            self.listbox.insert('end', f'✗ 跳转失败: {e}')
            return
        self.refresh()

    def current_name(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        text = self.listbox.get(sel[0])
        return text[len('[目录] '):] if text.startswith('[目录] ') else None

    def enter_dir(self):
        name = self.current_name()
        if name is None or self.ftp is None:
            return
        try:
            self.ftp.cwd(self.path.rstrip('/') + '/' + name)
            self.path = self._norm(self.ftp.pwd() or self.path.rstrip('/') + '/' + name)
        except Exception:
            return  # 不是目录（文件）或无权
        self.refresh()

    def go_up(self):
        if self.ftp is None or self.path in ('/', ''):
            return
        self.ftp.cwd('..')
        self.path = self._norm(self.ftp.pwd() or '/')
        self.refresh()

    def pick(self):
        if self.conn_info is None:
            return
        info = self.conn_info
        if info['user'] and info['user'] != 'anonymous':
            auth = f"{info['user']}:{info['pw']}@"
        else:
            auth = ''
        url = f'ftp://{auth}{info["host"]}:{info["port"]}{self.path}'
        self.on_select(url)
        self.top.destroy()


# ---------------- 拖拽窗口（tkinterdnd2，可选） ----------------
def run_gui():
    try:
        import tkinter as tk
        from tkinter import filedialog
        from tkinterdnd2 import DND_FILES, TkinterDnD
    except ImportError:
        return False
    import threading

    root = TkinterDnD.Tk()
    root.title('toms ⇄ MusicXML 转换')
    root.geometry('640x500')
    root.configure(bg='#f5f6fa')

    tip = tk.Label(root, text='把 .toms / .xml / .musicxml / .mxl 文件拖进窗口即可转换（可一次拖多个）\n'
                              '.toms → score.xml     .xml/.mxl → score.toms + hash_sums',
                   bg='#f5f6fa', fg='#333', font=('Microsoft YaHei UI', 11))
    tip.pack(pady=(16, 8))

    outrow = tk.Frame(root, bg='#f5f6fa')
    outrow.pack(fill='x', padx=16, pady=4)
    tk.Label(outrow, text='输出路径：', bg='#f5f6fa', fg='#222',
             font=('Microsoft YaHei UI', 10)).pack(side='left')
    out_var = tk.StringVar()
    entry = tk.Entry(outrow, textvariable=out_var, width=42,
                     font=('Consolas', 9), bg='white')
    entry.pack(side='left', fill='x', expand=True, padx=(0, 6))
    tk.Button(outrow, text='本地目录…', command=lambda: out_var.set(filedialog.askdirectory()),
              bg='#e8ecf2', relief='flat', font=('Microsoft YaHei UI', 9)).pack(side='left')
    tk.Button(outrow, text='手机 FTP…', command=lambda: FtpBrowser(root, out_var.set),
              bg='#e8ecf2', relief='flat', font=('Microsoft YaHei UI', 9)).pack(side='left', padx=(6, 0))
    tk.Label(root, text='留空=输出到源文件目录；本地目录用"本地目录…"选择，手机路径用"手机 FTP…"连接后选择（Windows 不支持直接浏览 FTP）',
             bg='#f5f6fa', fg='#666', font=('Microsoft YaHei UI', 9)).pack(anchor='w', padx=16)

    box = tk.Text(root, bg='white', fg='#222', font=('Consolas', 10),
                  relief='solid', bd=1, padx=10, pady=10)
    box.pack(fill='both', expand=True, padx=16, pady=(6, 10))
    box.tag_configure('ok', foreground='#0a7d32')
    box.tag_configure('err', foreground='#c0392b')

    def log(msg, tag=None):
        box.insert('end', msg + '\n', tag or ())
        box.see('end')

    def on_drop(event):
        files = root.tk.splitlist(event.data)
        out = parse_out_spec(out_var.get())
        for p in files:
            threading.Thread(target=run_one, args=(p, out), daemon=True).start()

    def run_one(p, out):
        r = convert(os.fsdecode(p), out)
        tag = 'ok' if r.startswith('✓') else 'err'
        root.after(0, log, r, tag)

    root.drop_target_register(DND_FILES)
    root.dnd_bind('<<Drop>>', on_drop)
    root.mainloop()
    return True


# ---------------- 命令行 / 拖图标模式 ----------------
def main():
    args = [os.fsdecode(a) for a in sys.argv[1:]]
    out_spec = None
    files = []
    i = 0
    while i < len(args):
        if args[i] == '--out' and i + 1 < len(args):
            out_spec = parse_out_spec(args[i + 1])
            i += 2
        else:
            files.append(args[i])
            i += 1
    if not files:
        if run_gui():
            return
        print(__doc__)
        print('提示：也可以把 .toms / .xml / .mxl 文件直接拖到本脚本图标上完成转换。')
        try:
            input('\n按回车退出...')
        except EOFError:
            pass
        return
    results = [convert(p, out_spec) for p in files]
    print('\n'.join(results))
    print('\n转换完成。按回车退出...')
    try:
        input()
    except EOFError:
        pass


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    main()
