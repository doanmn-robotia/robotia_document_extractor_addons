from pathlib import Path

PO_FILE = Path("vi_VN.po")


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


def header_key(block: str) -> str:
    lines = block.splitlines()
    headers = []
    for line in lines:
        if line.startswith("#"):
            headers.append(line)
        else:
            break
    return "\n".join(headers)


content = PO_FILE.read_text(encoding="utf-8")

blocks = list(iter_blocks(content))
blocks.sort(key=header_key)

PO_FILE.write_text("\n".join(blocks), encoding="utf-8")

print("Sorted blocks by header")
