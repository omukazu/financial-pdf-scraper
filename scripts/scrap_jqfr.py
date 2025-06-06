import json
import subprocess
from argparse import ArgumentParser
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
    # sentences = split_text_into_sentences(text)
    # char_index2sent_index = [i for i, s in enumerate(sentences) for _ in s]

    canvas = Canvas(out_file.name)
    for page in pages:
        canvas.setPageSize((page.width, page.height))
        canvas.setStrokeColorRGB(0.75, 0.75, 0.75)
        canvas.setLineWidth(0.5)
        for frame in page.frames:
            canvas.rect(frame.x0, frame.y0, max(frame.x1 - frame.x0, 1), frame.y1 - frame.y0)

        for line in page.lines:
            y0 = round(min(lc.y0 for lc in line["lt_chars"]))
            for lt_char in line["lt_chars"]:
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
                canvas.setFont(get_fontname(lt_char), lt_char.size)
                canvas.drawString(lt_char.x0, y0, lt_char.get_text())
        canvas.showPage()
    canvas.save()


def main():
    parser = ArgumentParser(description="script for scraping a Japanese quarterly financial report")
    parser.add_argument("IN_FILE", type=Path, help="path to input file")
    parser.add_argument("--debug", default=None, type=Path, help="path to debug log file")
    args = parser.parse_args()

    pages = extract_pages(args.IN_FILE)
    text = "".join(p.to_text(include_table=True, include_line_break=True) for p in pages)
    sentences = segment_text_into_sentences(text)
    print(json.dumps(sentences, ensure_ascii=False, indent=2))
    if args.debug:
        dump_pdf(pages, args.debug)


if __name__ == "__main__":
    main()
