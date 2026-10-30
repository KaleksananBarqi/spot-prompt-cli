"""Engine perender template Jinja2 untuk menghasilkan prompt akhir."""

import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

from spot_prompt.models import ExecutionConfig, IndicatorFacts

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
DEFAULT_TEMPLATE_NAME = "spot_dca_prompt.j2"


def get_template_environment() -> Environment:
    """Menginisialisasi environment Jinja2."""
    loader = FileSystemLoader(TEMPLATE_DIR)
    env = Environment(
        loader=loader,
        autoescape=select_autoescape(disabled_extensions=("j2",)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def render_spot_prompt(
    facts: IndicatorFacts,
    config: ExecutionConfig,
    template_name: str = DEFAULT_TEMPLATE_NAME,
) -> str:
    """Merender template prompt dengan fakta indikator dan konfigurasi eksekusi."""
    env = get_template_environment()
    template = env.get_template(template_name)
    rendered = template.render(facts=facts, config=config)
    return rendered
