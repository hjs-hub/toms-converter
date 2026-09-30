# toms-converter

**The ONE 智能钢琴 `.toms` 曲谱转换器 / The ONE Smart Piano `.toms` score converter**

将 Finale / MuseScore 导出的 MusicXML / MXL 曲谱转换为 The ONE 智能钢琴 App（`com.theonepiano.smartpiano`）可以正常打开的 `.toms` 文件。
Convert MusicXML / MusicXML-compressed (MXL) scores exported from Finale / MuseScore into `.toms` files that **The ONE Smart Piano** App (`com.theonepiano.smartpiano`) can open.

`.toms` 格式是通过逆向 App 自带曲谱得到的（文件头 `A3 DE 69` + RC4 + zlib）。本工具在打包前自动完成所有 App 兼容性修复，并生成配套的 `hash_sums` 校验文件。
The `.toms` format was reverse-engineered from the App's own downloaded scores (magic header `A3 DE 69` + RC4 + zlib). This tool applies all App compatibility fixes before packaging, then generates the matching `hash_sums` checksum file.

---

## 功能特性 / Features

- 🖱️ **拖拽 GUI**（tkinterdnd2）+ CLI 命令行模式 / Drag & drop GUI + CLI mode
- 📄 支持 `.musicxml` / `.xml` / `.mxl`（MuseScore 压缩 XML）/ Accepts `.musicxml` / `.xml` / `.mxl`
- 🔀 **2 part → 1 part 自动合并**（双谱表），保留原排版不动（App 只支持 1 part 多谱表）/ **2-part → 1-part auto merge** (2 staves), keeps the original layout untouched (the App only supports 1 part with multiple staves)
- 🎼 **MusicXML 4.0 → 3.0 头部降级**（兼容 MuseScore 4 导出）/ **MusicXML 4.0 → 3.0 header downgrade** (for MuseScore 4 exports)
- ⏬ **极低音自动修复**：所有 `octave 0` 音符（A0/G0/E0…）自动升 8 度——App 遇到它们会崩溃 / **Low-note auto fix**: all `octave 0` notes (A0/G0/E0…) are raised one octave — the App crashes on them
- 🔐 完整 `.toms` 封装：魔数头 + RC4（1024 步预热）+ zlib level 6（完整流含 Adler-32）/ Full `.toms` packaging: magic header + RC4 (1024-round warmup) + zlib level 6 (complete stream with Adler-32)
- ✅ 生成 `hash_sums`（`score.toms` 的 md5）/ Generates `hash_sums` (md5 of `score.toms`)
- 🌐 可选 FTP 上传到 App 曲谱目录（带远程路径浏览器）/ Optional FTP upload to the App's score directory (with a remote path browser)

---

## 使用方法 / Usage

```bash
# CLI 命令行
python toms2xml.py <输入.musicxml> --out <输出目录>

# GUI：直接运行，把文件拖进窗口即可
python toms2xml.py
```

输出固定文件名：`score.toms` 和 `hash_sums`。
Output files (fixed names): `score.toms` and `hash_sums`.

---

## 工作原理 / How it works

```
MusicXML ──► 头部标准化 / standardize header ──► 4.0→3.0 降级 / downgrade
        ──► 2 part 合并 / merge 2 parts ──► 极低音修复 / fix octave-0 notes
        ──► zlib(6) ──► RC4 ──► "A3 DE 69" + 密文 / payload
        ──► hash_sums = "<md5>  score.toms"
```

逆向结论与全部兼容性坑位记录在 [toms转换要点.md](toms转换要点.md)。
Reverse-engineering notes and all compatibility pitfalls are documented in [toms转换要点.md](toms转换要点.md).

---

## 环境要求 / Requirements

- Python 3.8+
- `tkinterdnd2`（仅 GUI 拖拽需要）/ only needed for GUI drag & drop
- 其余仅用标准库 / No other dependencies (stdlib only)

---

## 许可证 / License

MIT — 见 [LICENSE](LICENSE)。

---

## 免责声明 / Disclaimer

- 本项目用于处理用户合法拥有的曲谱，目标是实现与 App 私有格式的互通。
- 逆向对象是 App 自己的文件格式；**本仓库不含 App 内任何受版权保护的曲谱内容**。
- This project was built for interoperability with scores the user legally owns.
- The reverse-engineering targets the App's own file format; **no copyrighted score content from the App is included in this repository**.
