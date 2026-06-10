from types import SimpleNamespace

from src.services.prism_review_projection import prism_review_item_projection


def test_prism_review_projection_includes_tex_content_contract_without_raw_pending_content():
    content = (
        "\\documentclass{article}\\begin{document}"
        "Therefore, the analysis demonstrates a grounded claim \\cite{smith2026}."
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
    assert projection["preview"]["academic_style_contract"] == {
        "schema": "wenjin.prism.academic_style_contract.v1",
        "target_path": "main.tex",
        "basis": "bounded_academic_style_heuristic",
        "risk": "low",
        "academic_style_score": 4,
        "signal_count": 4,
        "anti_pattern_count": 0,
        "citation_key_count": 1,
        "signals": [
            "citation_grounding",
            "research_noun",
            "measured_claim",
            "formal_register",
        ],
        "anti_patterns": [],
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


def test_prism_review_projection_marks_academic_style_contract_high_risk_for_casual_ai_prose():
    content = (
        "\\documentclass{article}\\begin{document}"
        "As an AI, I think this thing is very good and basically awesome."
        "\\end{document}"
    )
    item = SimpleNamespace(
        id="review-3",
        target_kind="prism_file_change",
        target_ref_json={
            "latex_project_id": "latex-1",
            "logical_key": "project:main",
            "path": "main.tex",
        },
        status="pending",
        title="main.tex",
        summary="Casual rewrite",
        payload_json={
            "logical_key": "project:main",
            "path": "main.tex",
            "reason": "full_revision",
            "pending_hash": "sha256:pending",
            "pending_content": content,
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

    assert projection["preview"]["academic_style_contract"]["risk"] == "high"
    assert projection["preview"]["academic_style_contract"]["anti_patterns"] == [
        "ai_meta",
        "first_person_opinion",
        "casual_intensifier",
        "vague_noun",
    ]
    assert "pending_content" not in projection["preview"]


def test_prism_review_projection_sanitizes_upstream_academic_style_delta_contract():
    content = (
        "\\documentclass{article}\\begin{document}"
        "Therefore, the analysis indicates a robust effect \\cite{smith2026}."
        "\\end{document}"
    )
    item = SimpleNamespace(
        id="review-4",
        target_kind="prism_file_change",
        target_ref_json={
            "latex_project_id": "latex-1",
            "logical_key": "project:main",
            "path": "main.tex",
        },
        status="pending",
        title="main.tex",
        summary="Style-improving rewrite",
        payload_json={
            "logical_key": "project:main",
            "path": "main.tex",
            "reason": "full_revision",
            "pending_hash": "sha256:pending",
            "pending_content": content,
            "academic_style_contract": {
                "schema": "untrusted",
                "target_path": "main.tex",
                "basis": "member_self_check",
                "risk": "low",
                "academic_style_score": 4,
                "signal_count": 99,
                "anti_pattern_count": 99,
                "citation_key_count": 99,
                "signals": ["citation_grounding", "formal_register", "formal_register"],
                "anti_patterns": [],
                "raw_before": "As an AI, I think this thing is very good.",
                "style_delta": {
                    "schema": "untrusted-delta",
                    "baseline_academic_style_score": 1,
                    "score_delta": 999,
                    "improves_academic_style": False,
                    "raw_after": content,
                },
            },
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

    assert projection["preview"]["academic_style_contract"] == {
        "schema": "wenjin.prism.academic_style_contract.v1",
        "target_path": "main.tex",
        "basis": "member_self_check",
        "risk": "low",
        "academic_style_score": 4,
        "signal_count": 2,
        "anti_pattern_count": 0,
        "citation_key_count": 50,
        "signals": ["citation_grounding", "formal_register"],
        "anti_patterns": [],
        "style_delta": {
            "schema": "wenjin.prism.academic_style_delta.v1",
            "baseline_academic_style_score": 1,
            "pending_academic_style_score": 4,
            "score_delta": 3,
            "improves_academic_style": True,
        },
    }
    assert "raw_before" not in projection["preview"]["academic_style_contract"]
    assert "raw_after" not in projection["preview"]["academic_style_contract"]["style_delta"]
    assert "pending_content" not in projection["preview"]
