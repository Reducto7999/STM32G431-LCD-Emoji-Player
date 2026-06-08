from pathlib import Path
import re

from PIL import Image, ImageSequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRAME_DIR = Path(__file__).resolve().parent / "全部GIF图片帧"
OUTPUT_C = PROJECT_ROOT / "code" / "gif_animation.c"
OUTPUT_H = PROJECT_ROOT / "code" / "gif_animation.h"

MAX_COLORS = 8
DEFAULT_FRAME_DELAY_MS = 50
DEFAULT_MIRROR_X_FIX = 1
DEFAULT_MIRROR_Y_FIX = 0
LCD_WIDTH = 320
LCD_HEIGHT = 240
WHITE_RGB565 = 0xFFFF
SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}


def natural_key(path: Path):
    parts = re.split(r"(\d+)", path.stem)
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def rgb888_to_rgb565(r: int, g: int, b: int) -> int:
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def get_resize_filter():
    if hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS
    return Image.LANCZOS


def get_quantize_method():
    if hasattr(Image, "Quantize"):
        return Image.Quantize.MAXCOVERAGE
    return Image.MAXCOVERAGE


def resize_to_lcd_limit(image: Image.Image):
    width, height = image.size

    if width <= LCD_WIDTH and height <= LCD_HEIGHT:
        return image.copy(), image.size, image.size

    if width * LCD_HEIGHT >= height * LCD_WIDTH:
        new_width = LCD_WIDTH
        new_height = max(1, round(height * LCD_WIDTH / width))
    else:
        new_height = LCD_HEIGHT
        new_width = max(1, round(width * LCD_HEIGHT / height))

    resized = image.convert("RGBA").resize((new_width, new_height), get_resize_filter())
    return resized, image.size, resized.size


def image_to_rgb_on_white(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    white.paste(rgba, (0, 0), rgba.getchannel("A"))
    return white.convert("RGB")


def quantize_frame(image: Image.Image):
    rgb = image_to_rgb_on_white(image)
    quantized = rgb.quantize(
        colors=MAX_COLORS,
        method=get_quantize_method(),
        dither=Image.Dither.NONE,
    )

    raw_palette = quantized.getpalette() or []
    raw_indices = list(quantized.tobytes())

    remap = {}
    compact_indices = []
    palette = []

    for raw_index in raw_indices:
        if raw_index not in remap:
            new_index = len(remap)
            remap[raw_index] = new_index
            base = raw_index * 3
            r = raw_palette[base] if base < len(raw_palette) else 255
            g = raw_palette[base + 1] if base + 1 < len(raw_palette) else 255
            b = raw_palette[base + 2] if base + 2 < len(raw_palette) else 255
            palette.append(rgb888_to_rgb565(r, g, b))
        compact_indices.append(remap[raw_index])

    return compact_indices, palette, rgb.size


def encode_rle(indices):
    if not indices:
        return []

    encoded = []
    last = indices[0]
    count = 1

    for value in indices[1:]:
        if value == last and count < 255:
            count += 1
        else:
            encoded.extend((count, last))
            last = value
            count = 1

    encoded.extend((count, last))
    return encoded


def read_header_define(name: str, default: int) -> int:
    if not OUTPUT_H.exists():
        return default

    match = re.search(
        rf"#define\s+{re.escape(name)}\s+(\d+)",
        OUTPUT_H.read_text(encoding="ascii", errors="ignore"),
    )
    if match:
        return int(match.group(1))

    return default


def iter_input_frames():
    image_files = [
        path for path in FRAME_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    ]

    for path in sorted(image_files, key=natural_key):
        with Image.open(path) as image:
            if path.suffix.lower() == ".gif":
                for frame_number, frame in enumerate(ImageSequence.Iterator(image), start=1):
                    yield f"{path.stem}_{frame_number}", frame.copy()
            else:
                yield path.stem, image.copy()


def format_c_array(values, indent="  ", per_line=16):
    lines = []
    for i in range(0, len(values), per_line):
        chunk = values[i:i + per_line]
        lines.append(indent + ", ".join(chunk))
    return ",\n".join(lines)


def write_header(frame_count: int, first_size, frame_delay_ms: int, mirror_x_fix: int, mirror_y_fix: int):
    width, height = first_size
    text = f"""#ifndef __GIF_ANIMATION_H
#define __GIF_ANIMATION_H

#include "lcd.h"

#define GIF_FRAME_WIDTH   {width}
#define GIF_FRAME_HEIGHT  {height}
#define GIF_FRAME_COUNT   {frame_count}
#define GIF_MAX_COLORS    {MAX_COLORS}
#define GIF_FRAME_DELAY_MS {frame_delay_ms}
#define GIF_MIRROR_X_FIX  {mirror_x_fix}
#define GIF_MIRROR_Y_FIX  {mirror_y_fix}

void GIF_ShowFrame(u8 frameIndex);
void GIF_ShowNextFrame(void);

#endif /* __GIF_ANIMATION_H */
"""
    OUTPUT_H.write_text(text, encoding="ascii")


def write_source(frames):
    lines = [
        '#include "gif_animation.h"',
        "",
        "typedef struct",
        "{",
        "    const u8 *rleData;",
        "    const u16 *palette;",
        "    u16 width;",
        "    u16 height;",
        "    u32 runCount;",
        "    u8 paletteSize;",
        "} GifFrameInfo;",
        "",
    ]

    for index, frame in enumerate(frames, start=1):
        palette_values = [f"0x{value:04X}" for value in frame["palette"]]
        rle_values = [f"0x{value:02X}" for value in frame["rle"]]

        lines.append(f"static const u16 frame_{index}_palette[{len(palette_values)}] = {{")
        lines.append(format_c_array(palette_values, per_line=12))
        lines.append("};")
        lines.append("")

        lines.append(f"static const u8 frame_{index}_rle[{len(rle_values)}] = {{")
        lines.append(format_c_array(rle_values, per_line=16))
        lines.append("};")
        lines.append("")

    lines.extend([
        "static const GifFrameInfo gifFrames[GIF_FRAME_COUNT] = {",
    ])

    for index, frame in enumerate(frames, start=1):
        width, height = frame["size"]
        run_count = len(frame["rle"]) // 2
        palette_size = len(frame["palette"])
        comma = "," if index < len(frames) else ""
        lines.append(
            f"    {{ frame_{index}_rle, frame_{index}_palette, "
            f"{width}, {height}, {run_count}, {palette_size} }}{comma}"
        )

    lines.extend([
        "};",
        "",
        "static void GIF_FillRect(u16 row, u16 colLeft, u16 width, u16 height, u16 color)",
        "{",
        "    u16 r;",
        "    u16 c;",
        "",
        "    if((width == 0) || (height == 0))",
        "    {",
        "        return;",
        "    }",
        "",
        "    for(r = 0; r < height; r++)",
        "    {",
        "        LCD_SetCursor((u8)(row + r), colLeft + width - 1);",
        "        LCD_WriteRAM_Prepare();",
        "        for(c = 0; c < width; c++)",
        "        {",
        "            LCD_WriteRAM(color);",
        "        }",
        "    }",
        "}",
        "",
        "static void GIF_ClearOutsideImage(u16 rowTop, u16 colLeft, u16 width, u16 height)",
        "{",
        "    GIF_FillRect(0, 0, LCD_PIXEL_WIDTH, rowTop, White);",
        "    GIF_FillRect(rowTop + height, 0, LCD_PIXEL_WIDTH, LCD_PIXEL_HEIGHT - rowTop - height, White);",
        "    GIF_FillRect(rowTop, 0, colLeft, height, White);",
        "    GIF_FillRect(rowTop, colLeft + width, LCD_PIXEL_WIDTH - colLeft - width, height, White);",
        "}",
        "",
        "static void GIF_WriteRow(u16 lcdRow, u16 lcdColRight, const u16 *rowData, u16 width)",
        "{",
        "    u16 x;",
        "",
        "    LCD_SetCursor((u8)lcdRow, lcdColRight);",
        "    LCD_WriteRAM_Prepare();",
        "#if GIF_MIRROR_X_FIX",
        "    for(x = 0; x < width; x++)",
        "    {",
        "        LCD_WriteRAM(rowData[x]);",
        "    }",
        "#else",
        "    for(x = width; x > 0; x--)",
        "    {",
        "        LCD_WriteRAM(rowData[x - 1]);",
        "    }",
        "#endif",
        "}",
        "",
        "static void GIF_DrawRLEFrameCentered(const GifFrameInfo *frame)",
        "{",
        "    static u16 rowBuffer[LCD_PIXEL_WIDTH];",
        "    u16 drawWidth;",
        "    u16 drawHeight;",
        "    u16 srcXOffset;",
        "    u16 srcYOffset;",
        "    u16 lcdRowOffset;",
        "    u16 lcdColLeft;",
        "    u16 lcdColRight;",
        "    u32 run;",
        "    u16 x;",
        "    u16 y;",
        "",
        "    drawWidth = frame->width;",
        "    drawHeight = frame->height;",
        "    srcXOffset = 0;",
        "    srcYOffset = 0;",
        "    lcdRowOffset = 0;",
        "    lcdColLeft = 0;",
        "",
        "    if(drawWidth > LCD_PIXEL_WIDTH)",
        "    {",
        "        srcXOffset = (drawWidth - LCD_PIXEL_WIDTH) / 2;",
        "        drawWidth = LCD_PIXEL_WIDTH;",
        "    }",
        "    else",
        "    {",
        "        lcdColLeft = (LCD_PIXEL_WIDTH - drawWidth) / 2;",
        "    }",
        "",
        "    if(drawHeight > LCD_PIXEL_HEIGHT)",
        "    {",
        "        srcYOffset = (drawHeight - LCD_PIXEL_HEIGHT) / 2;",
        "        drawHeight = LCD_PIXEL_HEIGHT;",
        "    }",
        "    else",
        "    {",
        "        lcdRowOffset = (LCD_PIXEL_HEIGHT - drawHeight) / 2;",
        "    }",
        "",
        "    lcdColRight = lcdColLeft + drawWidth - 1;",
        "    GIF_ClearOutsideImage(lcdRowOffset, lcdColLeft, drawWidth, drawHeight);",
        "",
        "    run = 0;",
        "    x = 0;",
        "    y = 0;",
        "    while((run < frame->runCount) && (y < frame->height))",
        "    {",
        "        u8 count;",
        "        u8 colorIndex;",
        "        u16 color;",
        "",
        "        count = frame->rleData[run * 2];",
        "        colorIndex = frame->rleData[run * 2 + 1];",
        "        color = frame->palette[colorIndex];",
        "        run++;",
        "",
        "        while((count > 0) && (y < frame->height))",
        "        {",
        "            u16 span;",
        "            u16 xEnd;",
        "            u16 copyStart;",
        "            u16 copyEnd;",
        "            u16 copyX;",
        "",
        "            span = frame->width - x;",
        "            if(span > count)",
        "            {",
        "                span = count;",
        "            }",
        "",
        "            xEnd = x + span;",
        "            if((y >= srcYOffset) && (y < (srcYOffset + drawHeight)))",
        "            {",
        "                copyStart = x;",
        "                if(copyStart < srcXOffset)",
        "                {",
        "                    copyStart = srcXOffset;",
        "                }",
        "                copyEnd = xEnd;",
        "                if(copyEnd > (srcXOffset + drawWidth))",
        "                {",
        "                    copyEnd = srcXOffset + drawWidth;",
        "                }",
        "                for(copyX = copyStart; copyX < copyEnd; copyX++)",
        "                {",
        "                    rowBuffer[copyX - srcXOffset] = color;",
        "                }",
        "            }",
        "",
        "            x = xEnd;",
        "            count -= (u8)span;",
        "            if(x >= frame->width)",
        "            {",
        "                if((y >= srcYOffset) && (y < (srcYOffset + drawHeight)))",
        "                {",
        "#if GIF_MIRROR_Y_FIX",
        "                    GIF_WriteRow(lcdRowOffset + drawHeight - 1 - (y - srcYOffset), lcdColRight, rowBuffer, drawWidth);",
        "#else",
        "                    GIF_WriteRow(lcdRowOffset + y - srcYOffset, lcdColRight, rowBuffer, drawWidth);",
        "#endif",
        "                }",
        "                x = 0;",
        "                y++;",
        "            }",
        "        }",
        "    }",
        "}",
        "",
        "void GIF_ShowFrame(u8 frameIndex)",
        "{",
        "    if(frameIndex >= GIF_FRAME_COUNT)",
        "    {",
        "        frameIndex = 0;",
        "    }",
        "",
        "    GIF_DrawRLEFrameCentered(&gifFrames[frameIndex]);",
        "}",
        "",
        "void GIF_ShowNextFrame(void)",
        "{",
        "    static u8 frameIndex = 0;",
        "",
        "    GIF_ShowFrame(frameIndex);",
        "    frameIndex++;",
        "    if(frameIndex >= GIF_FRAME_COUNT)",
        "    {",
        "        frameIndex = 0;",
        "    }",
        "",
        "    HAL_Delay(GIF_FRAME_DELAY_MS);",
        "}",
        "",
    ])

    OUTPUT_C.write_text("\n".join(lines), encoding="ascii")


def main():
    if not FRAME_DIR.exists():
        raise FileNotFoundError(f"Input frame directory not found: {FRAME_DIR}")

    frames = []
    total_rle_bytes = 0
    total_palette_bytes = 0
    resized_frame_count = 0
    frame_delay_ms = read_header_define("GIF_FRAME_DELAY_MS", DEFAULT_FRAME_DELAY_MS)
    mirror_x_fix = read_header_define("GIF_MIRROR_X_FIX", DEFAULT_MIRROR_X_FIX)
    mirror_y_fix = read_header_define("GIF_MIRROR_Y_FIX", DEFAULT_MIRROR_Y_FIX)

    for name, image in iter_input_frames():
        prepared_image, original_size, size = resize_to_lcd_limit(image)
        if original_size != size:
            resized_frame_count += 1

        indices, palette, size = quantize_frame(prepared_image)
        rle = encode_rle(indices)
        frames.append({
            "name": name,
            "original_size": original_size,
            "size": size,
            "palette": palette,
            "rle": rle,
        })
        total_rle_bytes += len(rle)
        total_palette_bytes += len(palette) * 2

    if not frames:
        raise RuntimeError(f"No supported image files found in {FRAME_DIR}")

    write_header(len(frames), frames[0]["size"], frame_delay_ms, mirror_x_fix, mirror_y_fix)
    write_source(frames)

    print(f"Generated {OUTPUT_C}")
    print(f"Generated {OUTPUT_H}")
    print(f"Frames: {len(frames)}")
    print(f"First frame size: {frames[0]['size'][0]}x{frames[0]['size'][1]}")
    print(f"LCD limit: {LCD_WIDTH}x{LCD_HEIGHT}")
    print(f"Resized frames: {resized_frame_count}")
    print(f"Max colors per frame: {MAX_COLORS}")
    print(f"Frame delay: {frame_delay_ms} ms")
    print(f"Mirror X fix: {mirror_x_fix}")
    print(f"Mirror Y fix: {mirror_y_fix}")
    print(f"RLE data bytes: {total_rle_bytes}")
    print(f"Palette bytes: {total_palette_bytes}")
    print(f"Total image data bytes: {total_rle_bytes + total_palette_bytes}")


if __name__ == "__main__":
    main()
