from types import SimpleNamespace

from src.services.prism_review_projection import prism_review_item_projection


def test_prism_review_projection_includes_tex_content_contract_without_raw_pending_content():
    content = (
        "\\documentclass{article}\\begin{document}"
        "Grounded claim \\cite{smith2026}."
        "\\begin{equation}x=1\\end{equation}"
        "\\begin{table}\\begin{tabular}{cc}a&b\\end{tabular}\\end{table}"
        "\\end{document}"
    )
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
            "pending_content": content,
            "source_execution_id": "exec-1",
            "source_task_id": "manuscript_writer",
        },
        preview_json={
            "mode": "diff",
            "path": "main.tex",
            "pending_hash": "sha256:pending",
            "pending_content": content,
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
    assert projection["preview"]["semantic_contract"] == {
        "schema": "wenjin.prism.semantic_contract.v1",
        "target_path": "main.tex",
        "basis": "bounded_structural_heuristic",
        "preserves_claims": True,
        "preserves_citations": True,
        "preserves_equations": True,
        "preserves_tables": True,
        "risk": "low",
        "citation_key_count": 1,
        "has_equations": True,
        "has_tables": True,
    }
    assert "pending_content" not in projection["preview"]
    assert "pending_content" not in projection


def test_prism_review_projection_marks_semantic_contract_high_risk_for_invalid_tex():
    item = SimpleNamespace(
        id="review-2",
        target_kind="prism_file_change",
        target_ref_json={
            "latex_project_id": "latex-1",
            "logical_key": "project:main",
            "path": "main.tex",
        },
        status="pending",
        title="main.tex",
        summary="Risky manuscript revision",
        payload_json={
            "logical_key": "project:main",
            "path": "main.tex",
            "reason": "full_revision",
            "pending_hash": "sha256:pending",
            "pending_content": "\\documentclass{article}\\begin{document}Broken \\cite:bad}\\end{document}",
        },
        preview_json={
            "mode": "diff",
            "path": "main.tex",
            "pending_hash": "sha256:pending",
            "pending_content": "\\documentclass{article}\\begin{document}Broken \\cite:bad}\\end{document}",
        },
        result_json=None,
        created_at=None,
        updated_at=None,
        applied_at=None,
    )

    projection = prism_review_item_projection(item, execution_id="exec-1")

    assert projection["preview"]["content_contract"]["balanced_braces"] is False
    assert projection["preview"]["semantic_contract"]["risk"] == "high"
    assert projection["preview"]["semantic_contract"]["preserves_claims"] is False
    assert projection["preview"]["semantic_contract"]["preserves_citations"] is False
