from types import SimpleNamespace

from src.services.prism_review_projection import prism_review_item_projection


def test_prism_review_projection_includes_tex_content_contract_without_raw_pending_content():
    item = SimpleNamespace(
        id="review-1",
        target_kind="prism_file_change",
        target_ref_json={
            "latex_project_id": "latex-1",
            "logical_key": "project:main",
            "path": "main.tex",
        },
        status="pending",
        title="main.tex",
        summary="Full manuscript revision",
        payload_json={
            "logical_key": "project:main",
            "path": "main.tex",
            "reason": "full_revision",
            "pending_hash": "sha256:pending",
            "pending_content": "\\documentclass{article}\\begin{document}Draft\\end{document}",
            "source_execution_id": "exec-1",
            "source_task_id": "manuscript_writer",
        },
        preview_json={
            "mode": "diff",
            "path": "main.tex",
            "pending_hash": "sha256:pending",
            "pending_content": "\\documentclass{article}\\begin{document}Draft\\end{document}",
        },
        result_json=None,
        created_at=None,
        updated_at=None,
        applied_at=None,
    )

    projection = prism_review_item_projection(item, execution_id="exec-1")

    assert projection["preview"]["content_contract"] == {
        "path": "main.tex",
        "content_format": "latex_document",
        "latex_shape": "document",
        "balanced_braces": True,
    }
    assert "pending_content" not in projection["preview"]
    assert "pending_content" not in projection
