"""Builds the ASS subtitle file (libass) for a Short from its caption style.

Pure functions, no I/O, so the output is easy to test. Sizes are scaled by
min(width, height) / 1080, the same rule the browser preview uses.
"""
import re
from app.pipeline.short_catalog import FONTS, POSITIONS, RATIOS, SIZE_REFERENCE

_UNSAFE = re.compile(r"[\x00-\x1f\x7f{}\\]")


def output_size(ratio: str) -> tuple[int, int]:
    return RATIOS[ratio]


def _colour(hex_colour: str, opacity_percent: int = 100) -> str:
    """'#RRGGBB' -> ASS '&HAABBGGRR' (alpha 00 is opaque)."""
    value = hex_colour.lstrip("#")
    red, green, blue = value[0:2], value[2:4], value[4:6]
    alpha = round(255 * (100 - opacity_percent) / 100)
    return f"&H{alpha:02X}{blue}{green}{red}".upper()


def _timestamp(seconds: float) -> str:
    centis = max(0, round(seconds * 100))
    hours, centis = divmod(centis, 360000)
    minutes, centis = divmod(centis, 6000)
    secs, centis = divmod(centis, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{centis:02}"


def _clean(text: str, uppercase: bool) -> str:
    text = " ".join(_UNSAFE.sub(" ", text).split())
    return text.upper() if uppercase else text


def _karaoke(text: str, duration: float) -> str:
    """\\k tags that sweep the highlight across the words. Word timings are not
    kept, so each word gets a share of the line proportional to its length."""
    words = text.split()
    total_centis = max(len(words), round(duration * 100))
    weights = [len(word) + 1 for word in words]
    shares = [max(1, total_centis * weight // sum(weights)) for weight in weights]
    return " ".join(f"{{\\k{share}}}{word}" for share, word in zip(shares, words))


def build_ass(cues: list[dict], style: dict, ratio: str) -> str:
    """cues: [{start, end, text}] in seconds from the clip start; style: a ShortStyle dict."""
    width, height = output_size(ratio)
    scale = min(width, height) / SIZE_REFERENCE
    font = FONTS[style["font"]]
    position = style["position"] if style["position"] in POSITIONS else "bottom"
    alignment = {"bottom": 2, "middle": 5, "top": 8}[position]
    margin_v = 0 if position == "middle" else round(height * 0.08)
    margin_h = round(width * 0.06)

    if style["box"]:
        # libass draws the box in the outline colour, with `Outline` as its padding.
        border_style, outline = 3, round(10 * scale)
        outline_colour = _colour(style["box_color"], style["box_opacity"])
    elif style["outline"] and style["outline_width"] > 0:
        border_style, outline = 1, max(1, round(style["outline_width"] * scale))
        outline_colour = _colour(style["outline_color"])
    else:
        border_style, outline = 1, 0
        outline_colour = _colour("#000000")

    highlight = style["highlight"]
    primary = _colour(style["highlight_color"] if highlight else style["color"])
    secondary = _colour(style["color"])
    bold = -1 if font["bold"] else 0
    style_line = ",".join(str(value) for value in [
        "Default", font["family"], round(style["size"] * scale), primary, secondary, outline_colour,
        "&H00000000", bold, 0, 0, 0, 100, 100, 0, 0, border_style, outline, 0,
        alignment, margin_h, margin_h, margin_v, 1,
    ])
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,"
        "Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,"
        "MarginL,MarginR,MarginV,Encoding",
        f"Style: {style_line}", "",
        "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    for cue in cues:
        text = _clean(cue["text"], style["uppercase"])
        if not text or cue["end"] <= cue["start"]:
            continue
        body = _karaoke(text, cue["end"] - cue["start"]) if highlight else text
        lines.append(f"Dialogue: 0,{_timestamp(cue['start'])},{_timestamp(cue['end'])},Default,,0,0,0,,{body}")
    return "\n".join(lines) + "\n"
