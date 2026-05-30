from src.dataservice.domains.prism.adapters.latex import build_latex_adapter_metadata


def test_latex_adapter_metadata_uses_source_metadata() -> None:
    metadata = build_latex_adapter_metadata(
        latex_project_id="latex-1",
        main_file="main.tex",
        file_order={"root": ["main.tex"]},
        llm_config={"metadata": {"section_map": {"intro": "sections/intro.tex"}}},
        template_id="template-1",
    )

    assert metadata == {
        "latex_project_id": "latex-1",
        "main_file": "main.tex",
        "template_id": "template-1",
        "file_order": {"root": ["main.tex"]},
        "source_metadata": {"section_map": {"intro": "sections/intro.tex"}},
    }
