# Workflow Integration Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create implementation plan.

**Goal:** Connect Citation module with LaTeX compilation service for seamless academic document generation.

**Architecture:** Enhance compile_latex tool to accept citation_ids parameter, automatically fetch paper data, generate BibTeX content, and inject bibliography commands into LaTeX before Docker compilation.

**Tech Stack:** SQLAlchemy async, BibTeXExporter, Docker LaTeX provider, LangChain tools

---

## Overview

This design enables the LLM to seamlessly:
1. Reference saved papers from the workspace
2. Auto-generate BibTeX bibliography files
3. Compile LaTeX documents with correct citations in one tool call

## Architecture

```
User Request → LLM → compile_latex(citation_ids=[...])
                        ↓
                  Fetch Paper Data (SQLAlchemy)
                        ↓
                  Generate .bib Content (BibTeXExporter)
                        ↓
                  Inject into LaTeX
                        ↓
                  Docker Compilation (pdflatex → bibtex → pdflatex × 2)
                        ↓
                  Return PDF
```

## Core Components

### 1. Enhanced compile_latex Tool

**File:** `src/execution/tools.py`

**New Parameters:**
- `citation_ids: list[str]` - List of paper IDs to cite
- `bibliography_style: str` - Bibliography style (default: "plain")

**Workflow:**
1. Detect `citation_ids` parameter
2. Query paper data from database
3. Use BibTeXExporter to generate `.bib` content
4. Inject `\bibliography{references}` and `\bibliographystyle{style}` into LaTeX
5. Write `.bib` file to working directory
6. Execute Docker compilation with bibtex pass

### 2. LaTeX Template Processing

**File:** `src/execution/providers/latex_provider.py`

**Enhancements:**
- Auto-detect if LaTeX has `\bibliography{}` command
- If not provided and citation_ids exist, auto-add before `\end{document}`
- Generate BibTeX citation keys based on paper data

### 3. Citation Key Generation

```python
def generate_citation_key(paper: Paper) -> str:
    """Generate BibTeX citation key: FirstAuthorYear"""
    first_author = paper.authors[0]["name"].split()[-1] if paper.authors else "Unknown"
    year = paper.year or "n.d."
    return f"{first_author}{year}".replace(" ", "")
```

### 4. BibTeX Export Enhancement

Modify BibTeXExporter to use consistent citation keys that match what the LLM expects.

## Data Flow Example

**LLM Call:**
```python
compile_latex(
    latex_content=r"""
\documentclass{article}
\begin{document}
According to \cite{Smith2024}, the method is effective.
\end{document}
""",
    citation_ids=["uuid-1", "uuid-2"],
    bibliography_style="apalike"
)
```

**System Processing:**
1. Query papers for uuid-1, uuid-2
2. Generate `references.bib`:
```bibtex
@article{Smith2024,
  author = {Smith, John},
  title = {Deep Learning Methods},
  journal = {Nature},
  year = {2024},
  doi = {10.1234/example}
}
@article{Doe2023,
  author = {Doe, Jane},
  title = {Related Work},
  journal = {Science},
  year = {2023}
}
```
3. Modify LaTeX to add:
```latex
\bibliographystyle{apalike}
\bibliography{references}
```
4. Docker compile: pdflatex → bibtex → pdflatex × 2

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/execution/tools.py` | Modify | Enhance compile_latex with citation support |
| `src/execution/providers/latex_provider.py` | Modify | Add BibTeX processing logic |
| `src/academic/citation/bibtex/exporter.py` | Modify | Ensure consistent citation keys |
| `tests/execution/test_latex_citations.py` | Create | Integration tests |

## Error Handling

1. **Citation ID not found:** Return error message with list of valid IDs
2. **BibTeX compilation fails:** Capture bibtex output, return meaningful error
3. **Missing \cite{} in LaTeX:** Still add bibliography (valid for empty citations)

## Testing Strategy

1. Unit tests for citation key generation
2. Unit tests for bibliography injection
3. Integration test with mock database
4. End-to-end test with Docker (optional, requires Docker)

---

## Implementation Plan

See: `docs/plans/2026-03-11-workflow-integration-plan.md` (to be created)
