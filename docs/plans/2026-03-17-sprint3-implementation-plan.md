# Sprint 3: Literature Retrieval Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance literature retrieval quality: LLM-powered Tier 2 extraction, enriched TOC, fuzzy section matching, workspace full-text search, and Redis caching.

**Architecture:** Build on existing TOC-based navigation (no vector embeddings). Add LLM summarization to Tier 2 extraction, improve section matching with fuzzy logic, add PostgreSQL full-text search for cross-paper queries, cache hot paths in Redis.

**Tech Stack:** LangChain LLM (existing), PostgreSQL full-text search (to_tsvector), difflib, Redis caching

**Database:** Direct model changes (dev phase, no Alembic migration needed — user confirmed)

---

## Task 1: Tier 2 LLM Extraction — Fill section_summaries, key_concepts, entities

Fill the three placeholder fields in `_extract_tier2()`.

**Files:**
- Modify: `src/academic/services/extraction_service.py`
- Test: `tests/academic/services/test_extraction_tier2.py`

## Task 2: Enriched TOC in list_papers()

Return word_count, page_range, summary per TOC entry.

**Files:**
- Modify: `src/academic/literature/tools.py` (list_papers)
- Modify: `src/academic/literature/navigation/models.py` (TOCEntry fields)
- Test: `tests/academic/literature/test_enriched_toc.py`

## Task 3: Fuzzy Section Matching in find_entry() and get_section()

Support fuzzy title matching + section_path lookup.

**Files:**
- Modify: `src/academic/literature/navigation/models.py` (PaperTOC.find_entry)
- Modify: `src/academic/literature/tools.py` (get_section)
- Test: `tests/academic/literature/test_fuzzy_matching.py`

## Task 4: Workspace Full-Text Search Tool

New search_workspace() tool using PostgreSQL to_tsvector.

**Files:**
- Modify: `src/database/models/paper.py` (add GIN index to PaperSection)
- Create: `src/academic/literature/tools.py` (add search_workspace tool)
- Test: `tests/academic/literature/test_search_workspace.py`

## Task 5: Redis Cache Layer for Section Reads and TOC

Cache get_section() and list_papers() results in Redis.

**Files:**
- Modify: `src/academic/literature/navigation/section_loader.py`
- Modify: `src/academic/literature/tools.py`
- Test: `tests/academic/literature/test_redis_cache.py`

## Task 6: Integration Verification + Release Gate

Run full regression, update release gate.
