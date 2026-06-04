# Capability and Skill Content Optimization

Date: 2026-06-04

This record explains the upgraded Wenjin capability/skill seed content. It is intentionally about content contracts and workflow shape, not a new framework.

## Design Goal

The previous seeds defined the catalog shape but left most skills as one-line role placeholders. The optimized design makes each workspace workflow more autonomous and reviewable:

- Capability graphs are sequential when a later task depends on earlier work. Writers, drafters, and critics receive `upstream_outputs` instead of running in parallel with planners or researchers.
- Skills contain executable operating rules, output contracts, and quality gates.
- Workspace-specific rules are first-class quality gates, so thesis, SCI, proposal, software copyright, and patent workflows do not share a generic writing rubric.
- User confirmation is reserved for missing decisions, risky assumptions, legal/filing choices, and result-card acceptance. Routine research, synthesis, drafting, audit, and revision proceed through the Lead Agent workflow.

## External Inputs

The upgraded content is informed by public workflow patterns and official writing/filing references. It does not copy long prompt text from any repository.

- Academic manuscript structure and reporting: ICMJE manuscript preparation sections, EQUATOR reporting guideline lookup, PRISMA 2020 checklist/flow concepts, FAIR data principles, and COS TOP transparency principles.
- Proposal writing: NSF merit-review logic where no local funder rubric is available: why, what, how, success assessment, team/resource fit, and broader impact/benefit.
- Thesis writing: GB/T 7713.1-2025 thesis composition, formatting, abstract, reference, appendix, and academic-norm orientation. Local school templates remain authoritative when supplied.
- Software copyright: Chinese users and China software copyright registration rules around application form, identification materials, source program, documentation, proof documents, and consistency of software name/version/materials.
- Patent drafting: Chinese users and China/CNIPA patent application practice are the default. CNIPA application-file components and examination-practice constraints are primary; WIPO/PCT or overseas drafting rules are secondary references only when the user explicitly asks.
- Open workflow inspiration: LangChain `open_deep_research` uses clarify -> research brief -> supervisor/researcher loops -> final report generation; GPT Researcher uses planner/execution agents, source tracking, aggregation, and publication. Wenjin adapts those workflow patterns into capability phases and quality gates rather than importing prompts.

## Workspace Contracts

### Thesis

Primary concern: normative academic writing under a school template.

Workflow emphasis:
- Research pack: source search, synthesis matrix, source quality audit.
- Manuscript: chapter architecture, evidence analysis, draft, citation audit.
- Empirical analysis: analysis verification, figure/table specification, result writing.
- Revision: reviewer-style critique, rewrite, citation audit.
- Defense: critique, visual/slide material planning, answer preparation.
- Reference curation: search/update, source audit, citation cleanup.

Quality gates:
- `thesis_structure_matches_school_template`
- `chapter_claims_have_evidence`
- `abstract_matches_body`
- `references_follow_target_style`

### SCI

Primary concern: journal-facing manuscript quality and reproducibility.

Workflow emphasis:
- Use IMRaD or target journal structure.
- Apply reporting guideline awareness: EQUATOR lookup, PRISMA for systematic reviews, and study-type-specific checklists where supplied.
- Keep Methods, Results, Discussion, data availability, and limitations consistent.
- Treat data/code/figures as evidence that should be verified or marked unverified.

Quality gates:
- `reporting_guideline_checked`
- `imrad_or_journal_structure_respected`
- `methods_results_discussion_consistent`
- `data_code_availability_considered`

### Proposal

Primary concern: funder rubric alignment and feasibility.

Workflow emphasis:
- Convert ideas into problem -> objective -> work packages -> method -> metric -> milestone -> deliverable -> impact.
- Tie every background claim to a necessity, every aim to a method, and every method to an evaluation criterion.
- Surface resources, team basis, risks, mitigations, and missing call-specific rules.

Quality gates:
- `objective_method_metric_alignment`
- `review_criteria_explicitly_addressed`
- `feasibility_risk_mitigation_included`
- `milestones_and_deliverables_traceable`

### Software Copyright

Primary concern: registration material consistency, not academic novelty.

Default jurisdiction: China software copyright registration for Chinese users. Do not switch to generic copyright, US/EU software documentation, or marketing material unless the user explicitly asks.

Workflow emphasis:
- Build a material checklist around software name, version, owner, development mode, completion date, runtime environment, modules, source program, manual/document, screenshots, and proof documents.
- Generate application-form material and manuals in standardized, factual Chinese.
- Keep implemented features separate from planned features.
- Enforce consistency across application form, source headers, manual, screenshots, and evidence pack.

Quality gates:
- `application_form_source_manual_consistency`
- `software_name_version_consistent`
- `source_and_document_deposit_rules_checked`
- `no_claims_about_unimplemented_features`

### Patent

Primary concern: defensible claim scope and specification support.

Default jurisdiction: China/CNIPA patent application practice for Chinese users. Draft for Chinese invention or utility-model filing unless the user explicitly asks for PCT or another jurisdiction.

Workflow emphasis:
- Start with prior art, distinguishing features, technical problem, technical effect, and fallback positions.
- Draft claim tree before drafting prose.
- Make every claim term supported by description, embodiments, or drawings.
- Keep reference numerals and terminology consistent.
- Mark CNIPA formal-review, novelty/inventiveness, and attorney-review items explicitly.

Quality gates:
- `claim_terms_supported_by_description`
- `independent_claim_scope_not_overbroad`
- `embodiments_enable_claim_features`
- `drawings_reference_numerals_consistent`
- `novelty_risk_logged`

## Implementation Notes

- All visible multistep capability seeds now use one task per phase with linear `depends_on`.
- Downstream tasks receive `upstream_outputs: "{{phases}}"`.
- Each visible workspace capability has richer `brief_schema.properties` so the Chat Agent and Lead Agent have a better input contract.
- Each skill has:
  - role-specific operating rules;
  - a reviewable output contract;
  - quality gates stored in seed config.
- Claim / citation audit skills expose item-level schemas for `claim_evidence_map`, `citation_key_audit`, `unsupported_claims`, `fabrication_risks`, `missing_sources`, `required_fixes`, and `residual_risks`; these fields feed the Lead Agent quality gates and frontend Evidence Ledger.
- SCI `research_question_to_paper` uses a topic-generic sandbox method probe instead of hardcoded domain-specific probes; deterministic probes should remain method/assumption oriented unless a capability explicitly declares a domain.
- Hidden/internal sandbox smoke capability is left as a single deterministic sandbox workflow.

## Guardrails

Tests in `backend/tests/integration/test_capability_skill_seeds.py` now enforce:

- every visible multistep capability is sequential rather than parallel;
- downstream tasks receive rendered upstream phase outputs;
- each workspace declares domain-specific quality gates;
- every skill prompt has operating rules and an output contract.
- claim/citation audit skills keep renderable structured item schemas.
- visible SCI writing probes stay topic-generic rather than embedding one specific research domain.
