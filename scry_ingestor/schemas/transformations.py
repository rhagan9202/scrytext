"""Pydantic schemas for adapter transformation configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WordTransformationConfig(BaseModel):
    """Transformation options for the Word adapter."""

    model_config = ConfigDict(extra="forbid")

    strip_whitespace: bool = True
    paragraph_separator: str = "\n"
    extract_metadata: bool = True
    extract_tables: bool = False

    @field_validator("paragraph_separator")
    @classmethod
    def _validate_paragraph_separator(cls, value: str) -> str:
        if value == "":
            raise ValueError("paragraph_separator cannot be empty")
        return value


class PDFTransformationConfig(BaseModel):
    """Transformation options for the PDF adapter."""

    model_config = ConfigDict(extra="forbid")

    layout_mode: bool = False
    combine_pages: bool = True
    page_separator: str = "\n\n"
    max_text_chars_per_page: int | None = Field(default=None, ge=1)
    extract_metadata: bool = True
    extract_tables: bool = False
    extract_images: bool = False
    page_range: tuple[int, int] | None = None

    @field_validator("page_range", mode="before")
    @classmethod
    def _parse_page_range(cls, value: Any) -> tuple[int, int] | None:
        if value is None or value == []:
            return None
        if isinstance(value, (list, tuple)):
            if len(value) != 2:
                raise ValueError("page_range must contain exactly two entries")
            start, end = value
        elif isinstance(value, Mapping):
            start = value.get("start")
            end = value.get("end")
        else:
            raise ValueError("page_range must be a sequence of two integers")
        if start is None or end is None:
            raise ValueError("page_range requires both start and end values")
        return int(start), int(end)

    @model_validator(mode="after")
    def _validate_page_range_bounds(self) -> PDFTransformationConfig:
        if self.page_range is not None:
            start, end = self.page_range
            if start < 0:
                raise ValueError("page_range start must be non-negative")
            if end <= start:
                raise ValueError("page_range end must be greater than start")
        return self


class BeautifulSoupTransformationConfig(BaseModel):
    """Transformation options for the BeautifulSoup adapter."""

    model_config = ConfigDict(extra="forbid")

    include_text: bool = True
    text_separator: str = "\n"
    text_strip: bool = True
    max_text_chars: int | None = Field(default=None, ge=1)
    include_links: bool = True
    include_metadata: bool = True
    selectors: dict[str, str] = Field(default_factory=dict)
    include_raw: bool = False

    @field_validator("text_separator")
    @classmethod
    def _validate_text_separator(cls, value: str) -> str:
        if value == "":
            raise ValueError("text_separator cannot be empty")
        return value

    @field_validator("selectors", mode="before")
    @classmethod
    def _ensure_selectors_mapping(cls, value: Any) -> dict[str, str]:
        if value is None:
            return {}
        if isinstance(value, Mapping):
            result: dict[str, str] = {}
            for key, selector in value.items():
                if not isinstance(key, str):
                    raise ValueError("selector keys must be strings")
                if not isinstance(selector, str):
                    raise ValueError("selector values must be strings")
                if selector == "":
                    raise ValueError("selector values cannot be empty")
                result[key] = selector
            return result
        raise ValueError("selectors must be a mapping of strings to CSS selectors")


class RESTTransformationConfig(BaseModel):
    """Transformation options for the REST adapter."""

    model_config = ConfigDict(extra="forbid")

    response_format: Literal["auto", "json", "text", "bytes"] = "auto"

    @field_validator("response_format")
    @classmethod
    def _normalize_response_format(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"auto", "json", "text", "bytes"}:
            raise ValueError("response_format must be one of: auto, json, text, bytes")
        return normalized
