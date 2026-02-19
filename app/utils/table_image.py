import base64
import io


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
