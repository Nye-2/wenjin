from src.contracts.workspace_academic_map import AcademicWorkspaceMapV1, compact_workspace_map_summary


def test_academic_workspace_map_carries_bounded_research_assets() -> None:
    workspace_map = AcademicWorkspaceMapV1(
        workspace_id="ws-1",
        workspace_type="sci",
        generated_at="2026-06-19T00:00:00Z",
        topic_hints=["federated learning", "large language models"],
        library={
            "source_count": 2,
            "strong_sources": [
                {
                    "source_key": "library:paper-1",
                    "title": "Federated Fine-tuning of Large Language Models",
                    "year": 2025,
                    "tags": ["FedLLM"],
                    "quality_flags": ["model_web_search_verified"],
                }
            ],
            "citation_risks": ["1 source missing DOI"],
        },
        manuscript={
            "active_project_id": "project-1",
            "main_file": "main.tex",
            "sections": [
                {
                    "section_id": "related_work",
                    "path": "sections/20_related_work.tex",
                    "status": "draft",
                    "word_estimate": 830,
                }
            ],
            "pending_prism_changes": 1,
        },
        experiments={
            "datasets": [{"path": "/workspace/datasets/panel.csv", "content_hash": "sha256:abc"}],
            "scripts": [{"path": "/workspace/experiments/run.py", "last_status": "success"}],
            "artifacts": [
                {
                    "path": "/workspace/outputs/figures/ablation.png",
                    "kind": "figure",
                    "source_script": "/workspace/experiments/run.py",
                }
            ],
        },
        memory=[{"memory_id": "mem-1", "summary": "用户关注通信效率", "category": "context"}],
        decisions=[{"decision_id": "dec-1", "summary": "目标会议暂定 AAAI", "status": "active"}],
        open_questions=["是否已有 baseline？"],
    )

    payload = workspace_map.model_dump()

    assert payload["schema_version"] == "wenjin.academic_workspace_map.v1"
    assert workspace_map.library.strong_sources[0].source_key == "library:paper-1"
    assert workspace_map.experiments.datasets[0].path == "/workspace/datasets/panel.csv"


def test_compact_workspace_map_summary_removes_full_text_like_payloads() -> None:
    summary = compact_workspace_map_summary(
        {
            "schema_version": "wenjin.academic_workspace_map.v1",
            "workspace_id": "ws-1",
            "workspace_type": "sci",
            "generated_at": "2026-06-19T00:00:00Z",
            "topic_hints": ["FedLLM", "LoRA"],
            "library": {
                "source_count": 20,
                "strong_sources": [
                    {"source_key": "library:paper-1", "title": "Paper " + ("x" * 400), "abstract": "hidden"}
                ],
            },
            "manuscript": {
                "sections": [
                    {"section_id": "intro", "path": "sections/10_intro.tex", "content": "full text hidden"}
                ]
            },
            "experiments": {"datasets": [{"path": "/workspace/datasets/a.csv", "raw": "hidden"}]},
        }
    )

    assert summary["topic_hints"] == ["FedLLM", "LoRA"]
    assert "abstract" not in summary["library"]["strong_sources"][0]
    assert "content" not in summary["manuscript"]["sections"][0]
    assert "raw" not in summary["experiments"]["datasets"][0]
    assert len(summary["library"]["strong_sources"][0]["title"]) <= 160

