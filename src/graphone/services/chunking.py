import re


def semantic_chunks(text: str, maximum_chars: int) -> list[str]:
    """Keep sentence boundaries where possible so 413 recovery retains source context."""
    if len(text) <= maximum_chars:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > maximum_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(sentence[index : index + maximum_chars] for index in range(0, len(sentence), maximum_chars))
        elif current and len(current) + 1 + len(sentence) > maximum_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks

