from src.contracts.review_policy import project_review_policy


def test_workspace_visual_assets_always_require_explicit_review() -> None:
    projection = project_review_policy(
        review_mode="auto_draft",
        target_kind="workspace_asset",
        target_room="assets",
        target_ref=None,
        risk_level="medium",
    )

    assert projection.requires_explicit_review is True
    assert projection.batch_acceptable is False
    assert projection.suggested_selected is False
