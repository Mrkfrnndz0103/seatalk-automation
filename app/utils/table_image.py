import base64
import io
from typing import Any


def table_values_to_png_base64(values: list[list[str]]) -> str:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required for dashboard image capture") from exc

    rows = values if values else [[""]]
    row_count = max(len(rows), 1)
    col_count = max((len(row) for row in rows), default=1)
    normalized: list[list[str]] = []
    for row in rows:
        normalized.append([str(cell) if cell is not None else "" for cell in row] + [""] * (col_count - len(row)))
    if len(normalized) < row_count:
        normalized.extend([[""] * col_count for _ in range(row_count - len(normalized))])

    font = ImageFont.load_default()
    padding_x = 6
    padding_y = 5
    row_height = 24
    min_col_width = 64
    max_col_width = 220
    max_total_width = 3600
    grid_color = (216, 220, 226)
    header_fill = (244, 247, 250)
    body_fill = (255, 255, 255)
    text_fill = (25, 28, 31)

    def _text_width(text: str) -> int:
        if not text:
            return 0
        try:
            left, _, right, _ = font.getbbox(text)
            return max(0, right - left)
        except AttributeError:
            return int(font.getlength(text))

    def _clip_to_width(text: str, max_width: int) -> str:
        if not text:
            return ""
        if _text_width(text) <= max_width:
            return text
        ellipsis = "..."
        clipped = text
        while clipped and _text_width(clipped + ellipsis) > max_width:
            clipped = clipped[:-1]
        return (clipped + ellipsis) if clipped else ellipsis

    col_widths: list[int] = []
    for col_idx in range(col_count):
        max_text_width = 0
        for row in normalized:
            max_text_width = max(max_text_width, _text_width(row[col_idx]))
        col_widths.append(min(max_col_width, max(min_col_width, max_text_width + (padding_x * 2))))

    total_width = sum(col_widths) + 1
    if total_width > max_total_width:
        scale = max_total_width / total_width
        scaled = [max(48, int(width * scale)) for width in col_widths]
        scaled_width = sum(scaled) + 1
        while scaled_width > max_total_width:
            for idx in range(len(scaled)):
                if scaled[idx] > 48:
                    scaled[idx] -= 1
                    scaled_width -= 1
                    if scaled_width <= max_total_width:
                        break
        col_widths = scaled

    image_width = sum(col_widths) + 1
    image_height = (row_count * row_height) + 1
    image = Image.new("RGB", (image_width, image_height), body_fill)
    draw = ImageDraw.Draw(image)

    y = 0
    for row_idx, row in enumerate(normalized):
        x = 0
        for col_idx, text in enumerate(row):
            width = col_widths[col_idx]
            draw.rectangle(
                [x, y, x + width, y + row_height],
                fill=header_fill if row_idx == 0 else body_fill,
                outline=grid_color,
                width=1,
            )
            visible = _clip_to_width(text.strip(), width - (padding_x * 2))
            if visible:
                draw.text((x + padding_x, y + padding_y), visible, fill=text_fill, font=font)
            x += width
        y += row_height

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def table_grid_snapshot_to_png_base64(snapshot: dict[str, Any]) -> str:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required for dashboard image capture") from exc

    values: list[list[str]] = snapshot.get("values", []) or [[]]
    row_count = len(values)
    col_count = max((len(row) for row in values), default=0)
    if row_count == 0 or col_count == 0:
        return table_values_to_png_base64(values)

    row_heights_raw = snapshot.get("row_heights", []) or []
    col_widths_raw = snapshot.get("col_widths", []) or []
    backgrounds = snapshot.get("backgrounds", []) or []
    text_colors = snapshot.get("text_colors", []) or []
    font_sizes = snapshot.get("font_sizes", []) or []
    bold = snapshot.get("bold", []) or []
    horizontal_alignments = snapshot.get("horizontal_alignments", []) or []
    merges = snapshot.get("merges", []) or []

    row_heights = [(row_heights_raw[r] if r < len(row_heights_raw) else 21) for r in range(row_count)]
    col_widths = [(col_widths_raw[c] if c < len(col_widths_raw) else 100) for c in range(col_count)]
    row_heights = [max(14, int(h)) for h in row_heights]
    col_widths = [max(28, int(w)) for w in col_widths]

    max_width = 3600
    total_width = sum(col_widths) + 1
    if total_width > max_width:
        scale = max_width / total_width
        col_widths = [max(20, int(w * scale)) for w in col_widths]
        scaled_total = sum(col_widths) + 1
        while scaled_total > max_width:
            for idx in range(len(col_widths)):
                if col_widths[idx] > 20:
                    col_widths[idx] -= 1
                    scaled_total -= 1
                    if scaled_total <= max_width:
                        break

    x_offsets = [0]
    for width in col_widths:
        x_offsets.append(x_offsets[-1] + width)
    y_offsets = [0]
    for height in row_heights:
        y_offsets.append(y_offsets[-1] + height)

    image_width = x_offsets[-1] + 1
    image_height = y_offsets[-1] + 1
    image = Image.new("RGB", (image_width, image_height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    grid_color = (216, 220, 226)
    default_bg = (255, 255, 255)
    default_text = (36, 39, 42)

    normal_fonts: dict[int, Any] = {}
    bold_fonts: dict[int, Any] = {}

    def _load_font(size: int, is_bold: bool):
        size = max(8, min(20, size))
        cache = bold_fonts if is_bold else normal_fonts
        if size in cache:
            return cache[size]
        name = "DejaVuSans-Bold.ttf" if is_bold else "DejaVuSans.ttf"
        try:
            font = ImageFont.truetype(name, size=size)
        except Exception:
            font = ImageFont.load_default()
        cache[size] = font
        return font

    def _color_from_google(color: dict[str, float] | None, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
        if not color:
            return fallback
        r = color.get("red", 0.0)
        g = color.get("green", 0.0)
        b = color.get("blue", 0.0)
        return (
            max(0, min(255, int(float(r) * 255))),
            max(0, min(255, int(float(g) * 255))),
            max(0, min(255, int(float(b) * 255))),
        )

    def _measure_text(font: Any, text: str) -> tuple[int, int]:
        try:
            left, top, right, bottom = font.getbbox(text)
            return max(0, right - left), max(0, bottom - top)
        except Exception:
            mask = font.getmask(text)
            return int(mask.size[0]), int(mask.size[1])

    merge_owner: dict[tuple[int, int], tuple[int, int]] = {}
    merge_rects: dict[tuple[int, int], tuple[int, int, int, int]] = {}
    for merge in merges:
        sr = int(merge.get("start_row", 0))
        er = int(merge.get("end_row", 0))
        sc = int(merge.get("start_col", 0))
        ec = int(merge.get("end_col", 0))
        if sr < 0 or sc < 0 or er <= sr or ec <= sc:
            continue
        if sr >= row_count or sc >= col_count:
            continue
        er = min(er, row_count)
        ec = min(ec, col_count)
        merge_rects[(sr, sc)] = (sr, er, sc, ec)
        for r in range(sr, er):
            for c in range(sc, ec):
                merge_owner[(r, c)] = (sr, sc)

    for r in range(row_count):
        for c in range(col_count):
            owner = merge_owner.get((r, c))
            if owner and owner != (r, c):
                continue

            if owner == (r, c):
                sr, er, sc, ec = merge_rects[(r, c)]
            else:
                sr, er, sc, ec = r, r + 1, c, c + 1

            x0 = x_offsets[sc]
            y0 = y_offsets[sr]
            x1 = x_offsets[ec]
            y1 = y_offsets[er]

            bg = None
            if r < len(backgrounds) and c < len(backgrounds[r]):
                bg = backgrounds[r][c]
            fill = _color_from_google(bg, default_bg)

            draw.rectangle([x0, y0, x1, y1], fill=fill, outline=grid_color, width=1)

            text = values[r][c] if c < len(values[r]) else ""
            if not text:
                continue

            size = 10
            if r < len(font_sizes) and c < len(font_sizes[r]) and font_sizes[r][c]:
                size = int(font_sizes[r][c])
            is_bold = bool(r < len(bold) and c < len(bold[r]) and bold[r][c])
            font = _load_font(size, is_bold)

            txt_color = None
            if r < len(text_colors) and c < len(text_colors[r]):
                txt_color = text_colors[r][c]
            fill_color = _color_from_google(txt_color, default_text)

            align = "LEFT"
            if r < len(horizontal_alignments) and c < len(horizontal_alignments[r]):
                align = str(horizontal_alignments[r][c] or "LEFT").upper()

            pad_x = 5
            pad_y = 3
            box_w = max(0, x1 - x0 - (pad_x * 2))
            box_h = max(0, y1 - y0 - (pad_y * 2))

            text_w, text_h = _measure_text(font, text)

            draw_text = text
            if text_w > box_w and box_w > 0:
                ellipsis = "..."
                while draw_text:
                    trial = draw_text + ellipsis
                    w, _ = _measure_text(font, trial)
                    if w <= box_w:
                        draw_text = trial
                        break
                    draw_text = draw_text[:-1]
                if not draw_text:
                    draw_text = ellipsis
                text_w, text_h = _measure_text(font, draw_text)

            if align == "RIGHT":
                tx = x1 - pad_x - text_w
            elif align == "CENTER":
                tx = x0 + max(0, ((x1 - x0 - text_w) // 2))
            else:
                tx = x0 + pad_x
            ty = y0 + max(pad_y, (box_h - text_h) // 2 + pad_y)

            draw.text((tx, ty), draw_text, fill=fill_color, font=font)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")
