# toms-converter

Convert MusicXML / MusicXML-compressed (MXL) scores exported from Finale / MuseScore into `.toms` files that **The ONE Smart Piano** App (`com.theonepiano.smartpiano`) can open.

The `.toms` format was reverse-engineered from the App's own downloaded scores (magic header `A3 DE 69` + RC4 + zlib). This tool packages your own MusicXML with full App compatibility fixes, then generates the matching `hash_sums` checksum file.

## Features

- 🖱️ **Drag & drop GUI** (tkinterdnd2) + CLI mode
- 📄 Accepts `.musicxml` / `.xml` / `.mxl` (MuseScore-compressed XML)
- 🔀 **2-part → 1-part auto merge** (2 staves), keeps the original layout untouched (the App only supports 1 part with multiple staves)
- 🎼 **MusicXML 4.0 → 3.0 header downgrade** (MuseScore 4 exports)
- ⏬ **Low-note auto fix**: all `octave 0` notes (A0/G0/E0…) are raised one octave — the App crashes on them
- 🔐 Full `.toms` packaging: magic header + RC4 (1024-round warmup) + zlib level 6 (complete stream with Adler-32)
- ✅ Generates `hash_sums` (md5 of `score.toms`)
- 🌐 Optional FTP upload to the App's score directory (with a remote path browser)

## Usage

```bash
# CLI
python toms2xml.py <input.musicxml> --out <output_dir>

# GUI: just run it and drag the file into the window
python toms2xml.py
```

Output files (fixed names): `score.toms` and `hash_sums`.

## How it works

```
MusicXML ──► standardize header ──► downgrade 4.0→3.0 ──► merge 2 parts
        ──► fix octave-0 notes ──► zlib(6) ──► RC4 ──► "A3 DE 69" + payload
        ──► hash_sums = "<md5>  score.toms"
```

Reverse-engineering notes and all compatibility pitfalls are documented in [toms转换要点.md](toms转换要点.md).

## Requirements

- Python 3.8+
- `tkinterdnd2` (GUI drag & drop only)
- No other dependencies (uses only stdlib otherwise)

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

- This project was built for interoperability with scores the user legally owns.
- The reverse-engineering targets the App's own file format; **no copyrighted score content from the App is included in this repository**.
