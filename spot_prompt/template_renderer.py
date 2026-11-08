"""Modul kompatibilitas mundur untuk template renderer."""

from spot_prompt.models import ExecutionConfig, IndicatorFacts
from spot_prompt.pipeline import DEFAULT_TEMPLATE_NAME, TEMPLATE_DIR, PromptPipeline

_pipeline = PromptPipeline()


def get_template_environment():
    return _pipeline._jinja_env


def render_spot_prompt(
    facts: IndicatorFacts,
    config: ExecutionConfig,
    template_name: str = DEFAULT_TEMPLATE_NAME,
) -> str:
    if template_name != DEFAULT_TEMPLATE_NAME:
        custom_pipeline = PromptPipeline(template_name=template_name)
        return custom_pipeline._render(facts, config)
    return _pipeline._render(facts, config)
