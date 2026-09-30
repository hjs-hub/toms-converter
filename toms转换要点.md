# The ONE 智能钢琴 `.toms` 曲谱转换要点（完整备忘）

> 目标：把 Finale / MuseScore 导出的 MusicXML/MXL 转换成 The ONE 智能钢琴 App（`com.theonepiano.smartpiano`）能正常打开的 `score.toms` + `hash_sums`。
> 工具：`C:\Users\lenovo\Desktop\toms2xml.py`（拖拽 GUI + CLI，输出固定文件名）。
> 测试基准：App 曲库固定条目目录 `58b58868d6f1e5e5bb2c15531fe6ebe0`（=《Put Your Hands Up》，piano.db id=17944）。

---

## 1. `.toms` 文件格式（已逆向并验证）

| 段 | 内容 |
|---|---|
| 文件头 | 魔数 `A3 DE 69`（3 字节），App 据此判断"是本 App 的 .toms" |
| 加密 | RC4，key = `85 31 F8 3C 0A 1F AC 2B 04 BD FD B2 CB B3 1A 85`，预热 1024 步 |
| 压缩 | zlib（deflate），level 6 |

**打包顺序**：`明文 XML → zlib.compressobj(6) 完整 zlib 流 → RC4 加密 → 魔数+密文`。

**关键坑**：
- ❌ 手工 `78 9C` + raw deflate（缺 Adler-32 校验尾）→ App 的 `mz_uncompress` 校验失败，**必然打不开**。
- ✅ 必须用 `zlib.compressobj(6)` 生成完整流（自带 `78 9C` 头 + Adler-32 尾）。
- 头 3 字节不是 `A3 DE 69` → App 直接报"文件头不是 A3 DE 69，不是本 App 的 .toms 格式"。

**往返验证**：原版谱 `toms → xml → toms` 可字节级还原 → 封装链路本身正确，打不开的问题都在 XML 内容。

---

## 2. `hash_sums` 文件格式

内容固定为一行：

```
<score.toms 的 md5>  score.toms
```

（md5 与文件名之间是两个空格。）

---

## 3. App 曲库机制

- `piano.db`：`/data/user/0/com.theonepiano.smartpiano/databases/piano.db`
  - `PlayRecord.scoreHash` 列值 = score 目录名。
  - **App 只认数据库已登记的目录**，新目录不会被扫描 → 测试只能覆盖已有条目目录。
- 测试目录：`/sdcard/Android/data/com.theonepiano.smartpiano/files/score/<scoreHash>/`
  - 只覆盖 `score.toms` + `hash_sums` 两个文件。
- **测试流程**：FTP 覆盖上传 → **完全关闭 App 重开** → 才生效（不重开永远"打不开"）。

---

## 4. App 能解析的 MusicXML 特征（穷举结论）

### 4.1 头部（必须替换为标准头部）
- MuseScore 4 导出头部（`Leland` 字体、`miscellaneous-field`、`part-name print-object="no"` 等）→ App 解析失败。
- 用原版《分院帽》的 Finale 式头部模板（`STANDARD_HEAD`）替换后，音符内容完全不动即可打开。
- 工具已自动无脑套用。

### 4.2 极低音（octave 0）—— 最大的崩溃根因
- **App 只接受 octave ≥ 1 的音符**；octave 0（A0=midi21、G0=19、E0=16 等）会让 App 解析崩溃、整谱打不开。
- **修复**：所有 `<octave>0</octave>` 统一升 8 度（0→1），包括 A0（最保险，完全进入原版 42 首 octave 1-7 范围）。
- **历史教训（重要）**：正则匹配极低音时，pitch 内 step 与 octave 之间有 `\r\n` 换行，**必须用 `re.sub(r'<octave>0</octave>', ...)` 这类不依赖空白结构的写法**；用 `<step>([A-G])</step>(?:<alter>…)?<octave>…</octave>` 这类正则**匹配不到换行格式，修复静默失效**——之前大量"打不开"其实是这个 bug 导致极低音根本没修。

### 4.3 2part 合并（多声部谱）
- 原版 42 首全部是 **1 part 双谱表**（`<part>` 内 2 个 `<staff>`），**2 part 结构 App 不支持**。
- 合并规则：
  - 保留源谱自身排版（`<measure width>`、`<print new-system>`、`default-x`、`<direction>速度` 等）**只合并不重排**。
  - **backup 位置必须在 P1 音符后、P2 音符前**（早期 bug：backup 位置错误 → P2 左手时值=0）。
  - **divisions 归一化**：P1 divisions=12 / P2 divisions=4 时，P2 的 duration 按比例缩放到 P1 divisions（否则左手变 1/3 拍）。
  - 合并后 P2 音符加 `<staff>2</staff>`；voice 保留 1 也没问题（878 验证过 voice 错配不崩）。

### 4.4 tie / tied（延音线）
- App 支持 `<tie>` 与 `<tied>` 成对写法（`<tie type="start"/>` 在音符内 + `<tied>` 在 `<notations>` 内）。
- **悬空 start**（只有 start 没有对应 stop）会让 App 崩溃 → 工具需配对检查。
- tie + 附点（`stop+dot`）原版大量存在，不是问题。
- 多 start 交错（如 `['start','start','stop','stop']`）原版普遍存在，不是问题。

### 4.5 已验证"不是问题"（别浪费时间重试）
- ❌ 2part 单谱表直接打包 → 不行。
- ❌ 删 `<group>` / `<sound>` / 装饰（歌词/连音/三连音/符杠/极低音）→ 无效。
- ❌ divisions 48→24 归一化 / 整体 ×4 / 878 的 dynamics+voice 归一化 → 无效。
- ❌ 给谱套自建排版（每 2/4 小节强制换行）→ 用户明确要求"只转换不要动排版"。
- ✅ 有效路径只有：**头部标准化 + 忠实保留源排版 + 2part 合并（backup 正确 + divisions 缩放）+ octave 0 全部升 8 度**。

### 4.6 谱面引擎
- 不是 VexFlow，是 **cocos2d-x 自研 C++ `MusicXmlLoader`**（libsmartpiano-player.so 内符号：`loadFromBuffer`、`Score::importXML`、`UIScore::createWithXMLData`、`Measure::addNote`、`BackupXML`、`NoteXML`、`TiedXML`、`BeamCounter`、`TempoEvent` 等）。
- 时值 / 小节 / backup / chord / tie / beam 均受支持。

---

## 5. 三个测试谱的结论

| 源谱 | 来源 | 结构 | 状态 |
|---|---|---|---|
| `score_toms.xml` | Finale v27.4 | 2part P1/P2，601 音符 | ✅ 可打开（新版 backup 修复后未单独复测，逻辑更正确） |
| `87859bfd..xml` | MuseScore 4 | 1part，divisions=48，1910 音符，带歌词 | ✅ 可打开（验收版，与新工具输出字节一致） |
| `Untitled1.musicxml` | Finale v27.4 | 2part，P1 divisions=12/P2=4，1612 音符，21 个 cue | ✅ 可打开（极低音修复 + 工具正则 bug 修复后验证） |

已知未解疑问：878 显示 138 但播放感觉偏快（可能 divisions=48 与 App 内部换算有关，未证实，用户未再要求处理）。

---

## 6. 工具使用

```bash
# CLI：拖入 MusicXML/MXL 转换（输出固定 score.toms + hash_sums）
python toms2xml.py <源文件> --out <输出目录>

# 或直接双击运行，把 XML/MXL 拖进窗口；GUI 带本地目录 / FTP 选择器
```

工具自动完成：
1. 头部标准化（`STANDARD_HEAD`）
2. MusicXML 4.0 → 3.0 降级
3. 2part → 1part 合并（backup 位置修复 + divisions 缩放）
4. **octave 0 极低音全部升 8 度**
5. 完整 zlib + RC4 封装，输出 `score.toms`
6. 生成 `hash_sums`

---

## 7. FTP 测试流程

- 地址：`192.168.3.7:2122`，匿名登录。
- 上传目录：`/sdcard/Android/data/com.theonepiano.smartpiano/files/score/58b58868d6f1e5e5bb2c15531fe6ebe0/`
- 上传两个文件：`score.toms`、`hash_sums`（校验 md5 匹配）。
- **必须完全关闭 App 重开**再进曲库测试。

---

## 8. 主要文件

| 文件 | 说明 |
|---|---|
| `C:\Users\lenovo\Desktop\toms2xml.py` | 最终版转换工具（拖拽 GUI + CLI） |
| `C:\Users\lenovo\Doubao\chats\2026-09-26\new-chat\toms2xml.py` | 工作副本（同上） |
| `C:\Users\lenovo\Desktop\test_u1n\` | Untitled1 最终转换产物（已验收） |
| `C:\Users\lenovo\Desktop\test_final1\` | 878 验收产物 |
| `C:\Users\lenovo\Desktop\re_test0\` | score_toms 新版（backup 修复）产物 |
| `D:\score\` | 原版 42 首 score.toms（可开样本库） |
| `C:\Users\lenovo\Doubao\chats\2026-09-26\new-chat\piano.db` | 手机曲库数据库副本 |
