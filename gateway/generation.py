"""The request students send, and the fal-ai/flux-lora arguments it becomes.

The fields, defaults and ranges are those of the Modal app this gateway replaces
(github.com/abhilashab4/Indian-painting-generator, backend/modal_app.py), so students'
pages keep working. Guidance is bounded by fal's schema for fal-ai/flux-lora (0 to 35).

One deliberate difference: a prompt that does not name its style gets the style's phrase
appended. Tested on 20 November 2026 with a fixed seed, both LoRAs left a plain prompt
photographic and only drew a miniature once the phrase was in the prompt.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = ["FAL_MODEL", "GenerationRequest", "InvalidRequest", "Style", "fal_arguments", "parse_request", "styled_prompt"]

FAL_MODEL = "fal-ai/flux-lora"
# fal's faster inference path; same image quality at the same seed, about half the time.
ACCELERATION = "regular"

DEFAULT_STYLE = "kangra"
DEFAULT_STEPS = 20
DEFAULT_GUIDANCE = 3.5
DEFAULT_SIDE = 768
DEFAULT_LORA_SCALE = 1.0

STEPS_RANGE = (1, 50)
GUIDANCE_RANGE = (0.0, 35.0)
SIDE_RANGE = (256, 1536)
LORA_SCALE_RANGE = (0.0, 2.0)
PROMPT_MAX_CHARS = 2000

# FLUX works in 16-pixel blocks; the Modal app's diffusers pipeline rounded down the same way.
SIDE_MULTIPLE = 16
# Above one megapixel a PNG can pass Lambda's 6 MB response cap once base64-encoded,
# so larger images come back as JPEG.
PNG_MAX_PIXELS = 1024 * 1024


class InvalidRequest(ValueError):
    """The request body breaks the contract; the message says which field and why."""


@dataclass(frozen=True)
class Style:
    name: str
    lora_url: str
    phrase: str


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    style: str
    steps: int
    guidance: float
    width: int
    height: int
    lora_scale: float


def parse_request(body: Any, styles: Collection[str]) -> GenerationRequest:
    """Validate a decoded JSON body against the contract."""
    if not isinstance(body, Mapping):
        raise InvalidRequest("body must be a JSON object")
    return GenerationRequest(
        prompt=_prompt(body),
        style=_style(body, styles),
        steps=_whole_number(body, "steps", DEFAULT_STEPS, STEPS_RANGE),
        guidance=_number(body, "guidance", DEFAULT_GUIDANCE, GUIDANCE_RANGE),
        width=_side(body, "width"),
        height=_side(body, "height"),
        lora_scale=_number(body, "lora_scale", DEFAULT_LORA_SCALE, LORA_SCALE_RANGE),
    )


def fal_arguments(request: GenerationRequest, style: Style) -> dict[str, Any]:
    """The fal-ai/flux-lora input for a validated request in the given style."""
    return {
        "prompt": styled_prompt(request.prompt, style),
        "loras": [{"path": style.lora_url, "scale": request.lora_scale}],
        "num_inference_steps": request.steps,
        "guidance_scale": request.guidance,
        "image_size": {"width": request.width, "height": request.height},
        "output_format": "png" if request.width * request.height <= PNG_MAX_PIXELS else "jpeg",
        "acceleration": ACCELERATION,
        "enable_safety_checker": True,
    }


def styled_prompt(prompt: str, style: Style) -> str:
    """The prompt with the style's phrase appended, unless it already names the style."""
    if style.name.lower() in prompt.lower():
        return prompt
    return f"{prompt.rstrip(' .,;')}, {style.phrase}"


def _prompt(body: Mapping[str, Any]) -> str:
    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise InvalidRequest("prompt is required")
    if len(prompt) > PROMPT_MAX_CHARS:
        raise InvalidRequest(f"prompt must be at most {PROMPT_MAX_CHARS} characters")
    return prompt.strip()


def _style(body: Mapping[str, Any], styles: Collection[str]) -> str:
    style = body.get("style", DEFAULT_STYLE)
    if style not in styles:
        raise InvalidRequest(f"style must be one of: {', '.join(sorted(styles))}")
    return style


def _side(body: Mapping[str, Any], name: str) -> int:
    side = _whole_number(body, name, DEFAULT_SIDE, SIDE_RANGE)
    return side - side % SIDE_MULTIPLE


def _whole_number(body: Mapping[str, Any], name: str, default: int, bounds: tuple[float, float]) -> int:
    value = _number(body, name, default, bounds)
    if value != int(value):
        raise InvalidRequest(f"{name} must be a whole number")
    return int(value)


def _number(body: Mapping[str, Any], name: str, default: float, bounds: tuple[float, float]) -> float:
    value = body.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidRequest(f"{name} must be a number")
    low, high = bounds
    if not low <= value <= high:
        raise InvalidRequest(f"{name} must be between {low:g} and {high:g}")
    return float(value)
