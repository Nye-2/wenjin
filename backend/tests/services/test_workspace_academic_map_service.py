from src.services.workspace_academic_map_service import (
    build_academic_workspace_map_from_workspace_data,
    build_compact_academic_workspace_map_summary,
)


def test_build_academic_workspace_map_from_existing_workspace_data() -> None:
    workspace_map = build_academic_workspace_map_from_workspace_data(
        workspace_id="ws-1",
        workspace_type="sci",
        generated_at="2026-06-19T00:00:00Z",
        workspace_data={
            "related_documents": [
                {
                    "id": "source-1",
                    "citation_key": "smith2025fedlora",
                    "title": "Federated Fine-tuning of Large Language Models",
                    "year": 2025,
                    "doi": "10.0000/example",
                    "evidence_level": "strong",
                    "abstract_excerpt": "full abstract should stay out of the map summary",
                },
                {"id": "source-2", "title": "Unkeyed Paper"},
            ],
            "library_context": {"citation_keys": ["smith2025fedlora"]},
            "manuscript_context": {
                "project": {"project_id": "project-1", "main_file": "main.tex"},
                "sections": [{"section_id": "related_work", "path": "sections/20_related_work.tex"}],
                "pending_review_count": 2,
            },
            "workspace_file_summary": {
                "dataset_provenance": [{"path": "/workspace/datasets/panel.csv", "content_hash": "sha256:abc"}]
            },
            "sandbox_context": {
                "scripts": [{"path": "/workspace/experiments/run.py", "status": "success"}],
                "artifacts": [
                    {
                        "path": "/workspace/outputs/figures/ablation.png",
                        "kind": "figure",
                        "source_script": "/workspace/experiments/run.py",
                    }
                ],
            },
        },
    )

    assert workspace_map.library.source_count == 2
    assert workspace_map.library.strong_sources[0].source_key == "library:smith2025fedlora"
    assert workspace_map.library.citation_risks == ["1 sources missing citation keys"]
    assert workspace_map.manuscript.sections[0].path == "sections/20_related_work.tex"
    assert workspace_map.experiments.artifacts[0].path == "/workspace/outputs/figures/ablation.png"


def test_compact_academic_workspace_map_summary_is_bounded() -> None:
    summary = build_compact_academic_workspace_map_summary(
        workspace_id="ws-1",
        workspace_type="sci",
        workspace_data={
            "related_documents": [
                {
                    "id": f"source-{idx}",
                    "citation_key": f"key{idx}",
                    "title": "Very Long Paper Title " + ("x" * 500),
                    "abstract_excerpt": "raw abstract",
                }
                for idx in range(30)
            ],
            "sandbox_context": {"artifacts": [{"path": f"/workspace/outputs/{idx}.json"} for idx in range(30)]},
        },
    )

    assert len(summary["library"]["strong_sources"]) == 12
    assert len(summary["experiments"]["artifacts"]) == 12
    assert len(summary["library"]["strong_sources"][0]["title"]) <= 160
    assert "abstract_excerpt" not in summary["library"]["strong_sources"][0]

