"""Shared prompt-rendering plumbing for agent nodes."""

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

PROMPT_VERSION = "v1"  # bump when any template under prompts/ changes meaningfully

_env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent.parent / "prompts"),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_system(profile: dict) -> str:
    return _env.get_template("mentor_persona.md").render(**profile)


def render_task(template_name: str, schema_cls: type[BaseModel], **ctx) -> str:
    return _env.get_template(template_name).render(
        schema_json=json.dumps(schema_cls.model_json_schema(), separators=(",", ":")),
        **ctx,
    )
