import json
import subprocess
from argparse import ArgumentParser
from copy import deepcopy
from pathlib import Path

from pdfminer.layout import LTChar
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from financial_pdf_scraper.pdf import Page, extract_pages
from financial_pdf_scraper.sentence_segmentation import segment_text_into_sentences


def register_fonts(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    context_root = "https://github.com/google/fonts/raw/refs/heads/main/ofl"
    for url, basename in [
        (f"{context_root}/notosansjp/NotoSansJP%5Bwght%5D.ttf", "gothic.ttf"),
        (f"{context_root}/notoserifjp/NotoSerifJP%5Bwght%5D.ttf", "mincho.ttf"),
    ]:
        if (out_dir / basename).exists() is True:
            continue
        subprocess.run(
            ["wget", url, "--tries", "2", "--output-document", out_dir / basename, "--timeout", "30"], check=True
        )
    registerFont(TTFont("Gothic", f"{out_dir}/gothic.ttf"))
    registerFont(TTFont("Mincho", f"{out_dir}/mincho.ttf"))


def get_fontname(lt_char: LTChar) -> str:
    fontname = lt_char.fontname.decode("cp932") if lt_char.fontname is bytes else lt_char.fontname
    if any(q in fontname for q in ["Gothic", "ゴシック"]):
        return "Gothic"
    else:
        return "Mincho"


def dump_pdf(pages: list[Page], out_file: Path) -> None:
    register_fonts(Path("./assets/fonts"))

    # char_index = 0
    # text = "".join(p.to_text() for p in pages)
    # sentences = segment_text_into_sentences(text)
    # char_index2sent_index = [i for i, s in enumerate(sentences) for _ in s]

    canvas = Canvas(out_file.name)
    for page in pages:
        canvas.setPageSize((page.width, page.height))
        canvas.setStrokeColorRGB(0.75, 0.75, 0.75)
        canvas.setLineWidth(0.5)
        for frame in page.frames:
            canvas.rect(frame.x0, frame.y0, max(frame.x1 - frame.x0, 1), frame.y1 - frame.y0)

        for line in page.lines:
            y0 = round(min(tle.y0 for tle in line["tles"] if isinstance(tle, LTChar)))
            for tle in line["tles"]:
                if not isinstance(tle, LTChar):
                    continue
                # if char_index < len(char_index2sent_index):
                #     sent_index = char_index2sent_index[char_index]
                #     char_index += 1
                #     if predictions[sent_index] < 0.5:
                #         fill_color_rgb = (r, g, b)
                #     else:
                #         fill_color_rgb = (r, g, b)
                # else:
                #     fill_color_rgb = (0.75, 0.75, 0.75)
                canvas.setFillColorRGB(0.75, 0.75, 0.75)
                canvas.setFont(get_fontname(tle), tle.size)
                canvas.drawString(tle.x0, y0, tle.get_text())
        canvas.showPage()
    canvas.save()


def section_pages(pages: list[Page]) -> dict[str, list[Page]]:
    toc_index = 1
    for i, page in enumerate(pages):
        if "目次" in page.to_text():
            toc_index = i
            break

    sections = {
        "precede": pages[: toc_index + 1],
        "qualitative_information": pages[toc_index + 1 :],
        "succeed": [],
    }

    pages = pages[toc_index + 1 :]

    flag = False
    for i, page in enumerate(pages):
        if flag is True:
            break
        text = page.to_text()
        # 財政状態: に関する説明, の概況, に関する定性的情報, の分析, に関する概況, に関する分析
        # 将来予測情報: に関する説明 / 業績予想: に関する説明, に関する定性的情報 / 今後の見通し, 次期の見通し
        for query in [
            "財政状態に関する",
            "財政状態の",
            "将来予測情報に関する",
            "業績予想に関する",
            "今後の見通し",
        ]:
            if (char_index := text.find(query)) >= 0:
                if i == 0:
                    if char_index > 150:  # 3行
                        flag = True
                    # （１）当四半期決算の経営成績・財政状態の概況 パターン
                    elif (appendix := text[char_index + len(query) :].find(query)) >= 0:
                        char_index += len(query) + appendix
                        flag = True
                else:
                    flag = True

                if flag is True:
                    sub_page = deepcopy(page)
                    char_index2line_index = [
                        line_index
                        for line_index, line in enumerate(page.lines)
                        for _ in line["tles"]
                        if (line["table"] or line["header"] or line["footer"]) is False
                    ]
                    try:
                        line_index = char_index2line_index[char_index]
                        page.lines = page.lines[:line_index]
                        sub_page.lines = sub_page.lines[line_index:]
                    except IndexError:
                        sub_page.lines = []
                    sections["qualitative_information"] = pages[:i] + [page]
                    sections["succeed"] = [sub_page] + pages[i + 1 :]
                    break
    return sections


def main():
    parser = ArgumentParser(description="script for scraping a Japanese quarterly financial report")
    parser.add_argument("IN_FILE", type=Path, help="path to input file")
    parser.add_argument("--debug", default=None, type=Path, help="path to debug log file")
    args = parser.parse_args()

    pages = extract_pages(args.IN_FILE)

    text = "".join(p.to_text(include_table=True, include_line_break=True) for p in pages)
    sentences = segment_text_into_sentences(text)
    print(json.dumps(sentences, ensure_ascii=False, indent=2))

    sections = section_pages(pages)
    for key, values in sections.items():
        print(f"** {key} **")
        print("".join(p.to_text(include_table=True, include_line_break=True) for p in values))

    if args.debug:
        dump_pdf(pages, args.debug)


if __name__ == "__main__":
    main()
