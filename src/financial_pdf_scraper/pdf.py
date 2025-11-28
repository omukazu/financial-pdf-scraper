from collections import defaultdict
from dataclasses import dataclass
from itertools import chain, pairwise
from pathlib import Path

from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTAnno, LTChar, LTContainer, LTCurve, LTTextLine, TextLineElement
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser


@dataclass(frozen=True)
class Rect:
    x0: int
    y0: int
    x1: int
    y1: int

    def to_tuple(self) -> tuple[int, int, int, int]:
        return self.x0, self.y0, self.x1, self.y1


class Page:
    def __init__(self, page: PDFPage, layout) -> None:
        _, _, width, height = page.mediabox
        self.width = width
        self.height = height

        rects = self.extract_rects(layout)
        self.frames = self.get_frames(rects)

        lt_text_lines = self.extract_lt_text_lines(layout)
        self.lines = self.aggregate_lt_text_lines(lt_text_lines)

    def extract_rects(self, layout) -> list[Rect]:
        if isinstance(layout, LTCurve):
            try:
                rect = self.curve2rect(layout)
                if rect.x1 - rect.x0 < self.width * 5 / 6 or rect.y1 - rect.y0 < self.height * 5 / 6:
                    return [rect]
            except IndexError:
                pass
        elif isinstance(layout, LTContainer):
            instances = []
            for child in layout:
                instances.extend(self.extract_rects(child))
            return instances
        return []

    @staticmethod
    def curve2rect(curve: LTCurve) -> Rect:
        """曲線をその外接矩形に変換"""
        if curve is LTCurve:
            xs, ys = zip(*curve.pts)
            return Rect(x0=round(min(xs)), y0=round(min(ys)), x1=round(max(xs)), y1=round(max(ys)))
        else:
            return Rect(x0=round(curve.x0), y0=round(curve.y0), x1=round(curve.x1), y1=round(curve.y1))

    @staticmethod
    def get_frames(rects: list[Rect]) -> list[Rect]:
        """重複する矩形をそれらの外接矩形に集約"""
        y2xs = defaultdict(set)
        for rect in rects:
            for y in range(rect.y0, rect.y1 + 1):
                y2xs[y] |= {rect.x0, rect.x1}

        frames = []
        for rect in rects:
            if len(y2xs[round((rect.y0 + rect.y1) / 2)]) <= 2:
                continue
            frames.append(rect)
            overlapped = [
                f
                for f in frames
                if max(rect.x0, f.x0) <= min(rect.x1, f.x1) and max(rect.y0, f.y0) <= min(rect.y1, f.y1)
            ]
            frames = [f for f in frames if f not in overlapped]
            x0s, y0s, x1s, y1s = zip(*[f.to_tuple() for f in overlapped])
            frames.append(Rect(x0=min(x0s), y0=min(y0s), x1=max(x1s), y1=max(y1s)))
        return frames

    def extract_lt_text_lines(self, layout: object) -> list[LTTextLine]:
        """LTTextLineクラスのインスタンスを抽出"""
        if isinstance(layout, LTTextLine):
            return [layout]
        elif isinstance(layout, LTContainer):
            instances = []
            for child in layout:
                instances.extend(self.extract_lt_text_lines(child))
            return instances
        return []

    def aggregate_lt_text_lines(self, lt_text_lines: list[LTTextLine]) -> list[dict[str, list[LTChar] | bool]]:
        """抽出されたLTTextLineクラスのインスタンスを集約"""
        y2lt_text_lines = self.aggregate_lt_text_lines_by_y(lt_text_lines)

        aggregated = []
        for clustered in y2lt_text_lines.values():
            tles = [
                tle
                for tle in chain.from_iterable(
                    sorted(clustered, key=lambda x: x.x0)
                )  # x0が小さい順（左から右へ）にソート
                if self.is_valid_text_line_element(tle)
            ]
            self.remove_overlapping_lt_chars(tles)
            text = "".join(tle.get_text() for tle in tles)
            if text == "" or text.isspace():  # 空白文字のみの行も除外
                continue
            if len(tles) >= 1:
                min_x0 = round(min(tle.x0 for tle in tles if isinstance(tle, LTChar)))
                min_y0 = round(min(tle.y0 for tle in tles if isinstance(tle, LTChar)))
                max_x1 = round(max(tle.x1 for tle in tles if isinstance(tle, LTChar)))
                max_y1 = round(max(tle.y1 for tle in tles if isinstance(tle, LTChar)))
                aggregated.append(
                    {
                        "tles": tles,
                        "table": any(
                            f.x0 - 1 <= min_x0 and f.y0 - 1 <= min_y0 and f.x1 + 1 >= max_x1 and f.y1 + 1 >= max_y1
                            for f in self.frames
                        ),
                        "line_break": max_x1 < self.width * 5 / 6,
                        "header": max_y1 >= self.height * 0.95,
                        "footer": min_y0 <= self.height * 0.05,
                    }
                )
        if len(aggregated) >= 1:
            aggregated[-1]["line_break"] = False  # ページ末尾の行は右端に余白があっても改行しない
            for line in aggregated[1:-1]:
                # ページ先頭/末尾の行のみヘッダー/フッターとして扱う
                line["header"] = False
                line["footer"] = False
        return aggregated

    @staticmethod
    def aggregate_lt_text_lines_by_y(lt_text_lines: list[LTTextLine]) -> dict[str, list[LTTextLine]]:
        y2lt_text_lines = defaultdict(list)
        prev_y = 1_000_000
        # y0が大きい順（上から下へ）にソート
        for lt_text_line in sorted(lt_text_lines, key=lambda x: x.y0, reverse=True):
            y = round(lt_text_line.y0)
            # 前の行にほぼ重なる場合は集約
            if prev_y - y <= lt_text_line.height / 3:
                popped = y2lt_text_lines.pop(prev_y)
                y2lt_text_lines[y].extend(popped)
            y2lt_text_lines[y].append(lt_text_line)
            prev_y = y
        return dict(y2lt_text_lines)

    @staticmethod
    def is_valid_text_line_element(text_line_element: TextLineElement) -> bool:
        # TextLineElement = LTChar | LTAnno
        char = text_line_element.get_text()
        if isinstance(text_line_element, LTChar):
            return (char == " " or not char.isspace()) and text_line_element.x0 >= 0.0 and text_line_element.y0 >= 0.0
        elif isinstance(text_line_element, LTAnno):
            return char == " "
        else:
            return False

    @staticmethod
    def remove_overlapping_lt_chars(valid_tles: list[TextLineElement]) -> None:
        lt_chars = [tle for tle in valid_tles if isinstance(tle, LTChar)]
        overlapping_lt_chars = []
        for cur_lt_char, next_lt_char in pairwise(lt_chars):
            # 次の文字が重なっている場合は除外（だいたい見えない半角スペース）
            if cur_lt_char.x0 + cur_lt_char.width / 3 > next_lt_char.x0:
                overlapping_lt_chars.append(next_lt_char)
        for overlapping_lt_char in overlapping_lt_chars:
            valid_tles.remove(overlapping_lt_char)

    def to_text(
        self,
        include_table: bool = False,
        replacement: str = "",
        include_line_break: bool = False,
        include_header_and_footer: bool = False,
    ) -> str:
        text = ""
        for prev_line, cur_line, next_line in zip(
            self.lines[-1:] + self.lines[:-1], self.lines, self.lines[1:] + self.lines[:1]
        ):
            if cur_line["table"] is True:
                if include_table is True:
                    text += "\n" * int(prev_line["table"] is False)  # "<table>"
                    tr = ""  # "<tr>"
                    for cur_tle, next_tle in zip(cur_line["tles"], cur_line["tles"][1:] + cur_line["tles"][:1]):
                        tr += cur_tle.get_text()
                        try:
                            # 2文字以上離れていたら別カラムとみなす
                            distant = next_tle.x0 - cur_tle.x1 >= cur_tle.width * 2.125
                        except AttributeError:
                            distant = False
                        tr += "  " * int(distant)
                    tr += "\n"  # "</tr>"
                    text += tr
                    text += "\n" * int(next_line["table"] is False)  # "</table>"
                else:
                    text += replacement
            elif cur_line["header"] is True or cur_line["footer"] is True:
                if include_header_and_footer is True:
                    text += "".join(tle.get_text() for tle in cur_line["tles"])
                    text += "  " * cur_line["line_break"] * include_line_break
            else:
                text += "".join(tle.get_text() for tle in cur_line["tles"])
                text += "  " * cur_line["line_break"] * include_line_break
        return text


def extract_pages(in_file: Path) -> list[Page]:
    pages = []
    with in_file.open(mode="rb") as f:
        pdf_parser = PDFParser(f)
        pdf_document = PDFDocument(pdf_parser)
        pdf_resource_manager = PDFResourceManager()
        pdf_page_aggregator = PDFPageAggregator(pdf_resource_manager, laparams=LAParams(all_texts=True))
        pdf_page_interpreter = PDFPageInterpreter(pdf_resource_manager, pdf_page_aggregator)
        for page in PDFPage.create_pages(pdf_document):
            pdf_page_interpreter.process_page(page)
            layout = pdf_page_aggregator.get_result()
            pages.append(Page(page, layout))
    return pages
