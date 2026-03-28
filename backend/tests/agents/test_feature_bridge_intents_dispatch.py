"""feature_bridge_intents: every registry feature must have a param resolver."""

import inspect
from src.agents.lead_agent.feature_bridge_intents import _PARAM_RESOLVERS
from src.workspace_features.registry import iter_workspace_features


def test_every_feature_has_param_resolver():
    """Every registered workspace feature must have an entry in _PARAM_RESOLVERS."""
    missing = [
        f.id for f in iter_workspace_features()
        if f.id not in _PARAM_RESOLVERS
    ]
    assert not missing, f"Features missing param resolver: {missing}"


def test_param_resolvers_are_async_callables():
    """Every resolver in _PARAM_RESOLVERS must be an async callable."""
    non_async = [k for k, v in _PARAM_RESOLVERS.items() if not inspect.iscoroutinefunction(v)]
    assert not non_async, f"Non-async resolvers: {non_async}"
