from pathlib import Path

PO_FILE = Path("vi_VN.po")
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

kept_blocks = [
    block for block in iter_blocks(content)
    if TARGET not in block
]

PO_FILE.write_text("\n".join(kept_blocks), encoding="utf-8")

print("Removed blocks containing:", TARGET)
