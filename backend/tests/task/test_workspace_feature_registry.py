"""Registry invariants for workspace feature handlers."""

from src.workspace_features import iter_workspace_features, list_registered_handler_keys


def test_all_registry_features_have_registered_handlers():
    """Every workspace_feature registry entry should have a concrete handler."""
    declared_handler_keys = {
        feature.handler_key
        for feature in iter_workspace_features()
        if feature.task_type == "workspace_feature"
    }
    registered_handler_keys = set(list_registered_handler_keys())

    missing_handler_keys = sorted(declared_handler_keys - registered_handler_keys)
    assert missing_handler_keys == [], (
        "Missing concrete handlers for: "
        + ", ".join(missing_handler_keys)
    )
