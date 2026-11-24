"""Haiku 5.5 must get adaptive thinking (budget_tokens is a 400) and accept effort max."""

# Package Library
from kgfeg.model_registry import ModelConfig


def test_haiku_5_5_uses_adaptive_thinking_at_max_effort() -> None:
    """Haiku 5.5 settings use adaptive thinking and keep effort max."""

    settings = ModelConfig(
        model="anthropic:claude-haiku-5-5", anthropic_effort="max"
    ).kgs_settings("learning_components")

    assert settings["anthropic_thinking"] == {"type": "adaptive"}
    assert settings["anthropic_effort"] == "max"
