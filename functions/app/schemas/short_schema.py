import hashlib
import json
import re
import uuid
from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
FontKey = Literal["poppins_semibold", "poppins_bold", "anton", "bebas_neue", "archivo_black", "bangers"]
Ratio = Literal["9:16", "1:1", "4:5", "16:9"]
Background = Literal["blur", "solid", "fill"]
Position = Literal["top", "middle", "bottom"]

MAX_CAPTIONS = 60
MAX_CAPTION_CHARS = 120
MAX_TOTAL_CAPTION_CHARS = 4000
# Characters that could act as subtitle markup or break a line.
_UNSAFE = re.compile(r"[\x00-\x1f\x7f{}\\<>]")


class ShortStyle(BaseModel):
    """Caption look. Every field is bounded: it is user input that reaches the renderer."""
    model_config = ConfigDict(extra="forbid")

    font: FontKey = "poppins_semibold"
    size: int = Field(64, ge=24, le=120)
    color: HexColor = "#FFFFFF"
    outline: bool = True
    outline_color: HexColor = "#000000"
    outline_width: int = Field(3, ge=0, le=8)
    box: bool = False
    box_color: HexColor = "#000000"
    box_opacity: int = Field(60, ge=0, le=100)
    position: Position = "bottom"
    uppercase: bool = False
    highlight: bool = False
    highlight_color: HexColor = "#FFE600"


class ShortCaption(BaseModel):
    """One caption line. Times are seconds from the start of the clip."""
    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0, le=60)
    end: float = Field(gt=0, le=60)
    text: str = Field(min_length=1, max_length=MAX_CAPTION_CHARS)

    @model_validator(mode="after")
    def clean(self):
        self.text = " ".join(_UNSAFE.sub(" ", self.text).split())
        if not self.text:
            raise ValueError("Caption text must not be empty.")
        if self.end <= self.start:
            raise ValueError("A caption must end after it starts.")
        return self


class ShortOptions(BaseModel):
    """How a Short is rendered. The defaults reproduce the original look."""
    model_config = ConfigDict(extra="forbid")

    ratio: Ratio = "9:16"
    background: Background = "blur"
    background_color: HexColor = "#000000"
    style: ShortStyle = Field(default_factory=ShortStyle)
    # None: captions come from the transcript when rendering.
    captions: list[ShortCaption] | None = Field(default=None, max_length=MAX_CAPTIONS)


_OPTION_FIELDS = set(ShortOptions.model_fields)


class ShortRange(BaseModel):
    start_time: int = Field(ge=0, strict=True)
    end_time: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def validate_range(self):
        if not 20 <= self.end_time - self.start_time <= 60:
            raise ValueError("A Short must be 20 to 60 seconds long.")
        return self


class ShortRequest(ShortRange, ShortOptions):
    @model_validator(mode="after")
    def validate_captions(self):
        if self.captions is None:
            return self
        duration = self.end_time - self.start_time
        if not self.captions:
            raise ValueError("Send at least one caption, or omit captions to use the transcript.")
        if sum(len(c.text) for c in self.captions) > MAX_TOTAL_CAPTION_CHARS:
            raise ValueError("Captions are too long.")
        previous_end = 0.0
        for caption in self.captions:
            if caption.end > duration + 0.001:
                raise ValueError("A caption ends after the clip does.")
            if caption.start < previous_end - 0.001:
                raise ValueError("Captions must be in order and must not overlap.")
            previous_end = caption.end
        return self

    def options_dict(self) -> dict | None:
        """The render options to store, or None when they are all defaults."""
        current = self.model_dump(include=_OPTION_FIELDS)
        return None if current == ShortOptions().model_dump() else current

    def options_hash(self) -> str:
        """Identifies one look of one range; '' for the default look (also what
        rows created before styles existed carry)."""
        options = self.options_dict()
        if options is None:
            return ""
        return hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()


class ShortResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    video_id: uuid.UUID
    start_time: int
    end_time: int
    status: Literal["queued", "rendering", "completed", "failed", "expired"]
    error_code: str | None
    options: dict | None = None
    created_at: datetime
    expires_at: datetime


class ShortPresetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=40)
    style: ShortStyle

    @model_validator(mode="after")
    def clean_name(self):
        self.name = " ".join(_UNSAFE.sub(" ", self.name).split())
        if not self.name:
            raise ValueError("Preset name must not be empty.")
        return self


class ShortPresetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    style: dict
    created_at: datetime
