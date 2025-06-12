import re

CONVERTER = {
    "（": "$FULLWIDTH_LEFT_PARENTHESIS",
    "(": "$LEFT_PARENTHESIS",
    "「": "$LEFT_CORNER_BRACKET",
    "“": "$LEFT_DOUBLE_QUOTATION_MARK",
    "）": "$FULLWIDTH_RIGHT_PARENTHESIS",
    ")": "$RIGHT_PARENTHESIS",
    "」": "$RIGHT_CORNER_BRACKET",
    "”": "$RIGHT_DOUBLE_QUOTATION_MARK",
}
INVERTER = {v: k for k, v in CONVERTER.items()}


def segment_text_into_sentences(text: str, punct_marks: str = "。") -> list[str]:
    if "." in punct_marks and "\." not in punct_marks:
        raise ValueError('must escape period (".")')

    balanced = _balance(text)

    sentences = []
    period_pat = re.compile(rf"[^{punct_marks}]*{punct_marks}+|[^{punct_marks}]+$")
    for line in re.split(r"(?<=\n)(?=.)", balanced):  # 改行記号を残してsplit
        sentences += period_pat.findall(line)
    sentences = _merge_sentences(sentences)

    for i in range(len(sentences)):
        for key, value in INVERTER.items():
            sentences[i] = sentences[i].replace(key, value)
    return sentences


def _balance(text: str) -> str:
    """escape unclosed parentheses/quotation marks"""
    balanced = list(text)
    stack = {}
    for i, char in enumerate(text):
        if char in {"（", "(", "「", "“"}:
            stack[i] = char
        elif char in {"）", ")", "」", "”"}:
            for key, value in sorted(stack.items(), reverse=True):
                # key < i
                if (
                    value == "（"
                    and char in {"）", ")"}
                    or value == "("  # == > and > or
                    and char in {"）", ")"}
                    or value == "「"
                    and char == "」"
                    or value == "“"
                    and char == "”"
                ):
                    del stack[key]
                    break
            else:
                balanced[i] = CONVERTER[char]
    for key, value in stack.items():
        balanced[key] = CONVERTER[value]
    return "".join(balanced)


def _merge_sentences(sentences: list[str]) -> list[str]:
    merged_sentences = []
    parenthesis_level = 0
    quotation_level = 0
    buffer = ""
    while sentences:
        sentence = sentences.pop(0)

        parenthesis_level += sentence.count("（") - sentence.count("）")
        parenthesis_level += sentence.count("(") - sentence.count(")")
        quotation_level += sentence.count("「") - sentence.count("」")
        quotation_level += sentence.count("“") - sentence.count("”")

        if parenthesis_level == quotation_level == 0:
            merged_sentences.append(buffer + sentence)
            buffer = ""
        else:
            if "\n" in sentence:
                sentence, rest = sentence.split("\n", maxsplit=1)
                merged_sentences.append(buffer + sentence)
                sentences.insert(0, rest)
                parenthesis_level = 0
                quotation_level = 0
                buffer = ""
            else:
                buffer += sentence
    if buffer:
        merged_sentences.append(buffer)
    return merged_sentences
