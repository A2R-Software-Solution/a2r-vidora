"""What a Short can look like: fonts, ratios and built-in style presets.

One place, so the API, the renderer and the frontend editor agree. Font files
are bundled in functions/assets/fonts (SIL Open Font License, licences beside
them): the renderer never downloads a font.
"""
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"

# key -> label, file, family name inside the file (what libass matches), bold flag.
FONTS = {
    "poppins_semibold": {"label": "Poppins SemiBold", "file": "Poppins-SemiBold.ttf", "family": "Poppins SemiBold", "bold": False},
    "poppins_bold": {"label": "Poppins Bold", "file": "Poppins-Bold.ttf", "family": "Poppins", "bold": True},
    "anton": {"label": "Anton", "file": "Anton-Regular.ttf", "family": "Anton", "bold": False},
    "bebas_neue": {"label": "Bebas Neue", "file": "BebasNeue-Regular.ttf", "family": "Bebas Neue", "bold": False},
    "archivo_black": {"label": "Archivo Black", "file": "ArchivoBlack-Regular.ttf", "family": "Archivo Black", "bold": False},
    "bangers": {"label": "Bangers", "file": "Bangers-Regular.ttf", "family": "Bangers", "bold": False},
}

# ratio -> (width, height) of the rendered video.
RATIOS = {
    "9:16": (720, 1280),
    "1:1": (720, 720),
    "4:5": (720, 900),
    "16:9": (1280, 720),
}

# Captions in Devanagari (Hindi) use this font: none of the Latin fonts above has the glyphs.
DEVANAGARI_FONT = {"file": "NotoSansDevanagari-Bold.ttf", "family": "Noto Sans Devanagari"}

BACKGROUNDS = ("blur", "solid", "fill")
POSITIONS = ("top", "middle", "bottom")

# Font sizes and outline widths are in px of a 1080-px-wide frame; both the
# renderer and the browser preview scale them by min(width, height) / 1080.
SIZE_REFERENCE = 1080

PRESETS = {
    "clean": {"label": "Clean", "style": {"font": "poppins_semibold", "size": 64, "color": "#FFFFFF",
              "outline": True, "outline_color": "#000000", "outline_width": 3, "box": False,
              "position": "bottom", "uppercase": False, "highlight": False}},
    "bold": {"label": "Bold", "style": {"font": "anton", "size": 80, "color": "#FFFFFF",
             "outline": True, "outline_color": "#000000", "outline_width": 5, "box": False,
             "position": "bottom", "uppercase": True, "highlight": False}},
    "karaoke": {"label": "Karaoke", "style": {"font": "poppins_bold", "size": 64, "color": "#FFFFFF",
                "outline": True, "outline_color": "#000000", "outline_width": 3, "box": False,
                "position": "bottom", "uppercase": False, "highlight": True, "highlight_color": "#FFE600"}},
    "minimal": {"label": "Minimal", "style": {"font": "poppins_semibold", "size": 48, "color": "#FFFFFF",
                "outline": False, "box": True, "box_color": "#000000", "box_opacity": 55,
                "position": "bottom", "uppercase": False, "highlight": False}},
    "pop": {"label": "Pop", "style": {"font": "bangers", "size": 84, "color": "#FFE600",
            "outline": True, "outline_color": "#000000", "outline_width": 5, "box": False,
            "position": "middle", "uppercase": True, "highlight": False}},
}


def devanagari_font_file() -> Path:
    return FONT_DIR / DEVANAGARI_FONT["file"]


def font_file(key: str) -> Path:
    return FONT_DIR / FONTS[key]["file"]
