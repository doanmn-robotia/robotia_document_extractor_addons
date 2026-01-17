from pathlib import Path

PO_FILE = Path("vi_VN(1).po")
OUT_FILE = Path("matched.po")

TARGET = "/static/src/xml/settings"


def iter_blocks(text: str):
    block = []
    for line in text.splitlines(keepends=True):
        if line.strip() == "" and block:
            yield "".join(block)
            block = []
        else:
            block.append(line)
    if block:
        yield "".join(block)


content = PO_FILE.read_text(encoding="utf-8")

matched_blocks = [
    block for block in iter_blocks(content)
    if TARGET in block
]

OUT_FILE.write_text("\n".join(matched_blocks), encoding="utf-8")

print(f"Matched {len(matched_blocks)} block(s)")
