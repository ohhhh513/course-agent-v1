"""网页题面排版规范化与原文偏移映射；不做模糊或语义相似匹配。"""
from html import unescape
import re
import unicodedata


def canonical(text: str):
    # 每个规范化字符保留原文范围，匹配后仍用真实片段核对题图。
    units = [(char, i, i + 1) for i, char in enumerate(text)]

    def rewrite(pattern, replace, flags=0):
        nonlocal units
        value = ''.join(item[0] for item in units)
        updated, cursor = [], 0
        for match in re.finditer(pattern, value, flags):
            updated.extend(units[cursor:match.start()])
            replacement = replace(match)
            if replacement:
                start, end = units[match.start()][1], units[match.end() - 1][2]
                updated.extend((char, start, end) for char in replacement)
            cursor = match.end()
        updated.extend(units[cursor:])
        units = updated

    rewrite(r'&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);', lambda m: unescape(m[0]))
    units = [(c, start, end) for char, start, end in units for c in unicodedata.normalize('NFKC', char)]
    rewrite(r'!\[[^\]\n]*\]\([^\n]*?\)|<img\b[^>]*>', lambda m: '', re.I)
    rewrite(r'(?m)^```[^\n]*\n|^```\s*$', lambda m: '')
    rewrite(r'`([^`]+)`|\*\*([^*]+)\*\*', lambda m: m[1] or m[2])
    for _ in range(2):
        rewrite(r'\\([^a-zA-Z0-9\s])', lambda m: m[1] if ord(m[1]) < 128 else m[0])
    aliases = {'。': '.', '≤': '<=', '≥': '>=', '≠': '!=', '−': '-'}
    units = [(c, start, end) for char, start, end in units for c in aliases.get(char, char) if not c.isspace()]
    return ''.join(item[0] for item in units), [(item[1], item[2]) for item in units]


def source_excerpt(content: str, evidence: str) -> str | None:
    if evidence in content:
        return evidence
    wanted, _ = canonical(evidence)
    if not wanted:
        return None
    value, positions = canonical(content)
    index = value.find(wanted)
    if index < 0:
        return None
    start, end = positions[index][0], positions[index + len(wanted) - 1][1]
    # 保留紧邻片段边界的图片；图片仍须出现在真实来源而非模型编写的证据中。
    tail = re.match(r'\s*(?:!\[[^\]\n]*\]\([^\n]*?\)|<img\b[^>]*>)', content[end:], re.I)
    if tail:
        end += tail.end()
    prefix = re.search(r'(?:!\[[^\]\n]*\]\([^\n]*?\)|<img\b[^>]*>)\s*$', content[:start], re.I)
    if prefix:
        start = prefix.start()
    return content[start:end]
