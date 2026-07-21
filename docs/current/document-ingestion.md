# Document ingestion

Wenjin seals readable uploads as content-addressed `MissionInputManifest` objects before a Mission can consume them. The request path never executes macros, embedded objects, formulas, or document-provided code.

## Native extraction

| Format | Extractor | Notes |
|---|---|---|
| PDF | `pdf_text` | PyMuPDF page text; layout/OCR preprocessing remains available for scanned PDFs. |
| TXT, Markdown, CSV, TSV, JSON, source files | `plain_text` | UTF-8 text with bounded replacement for invalid bytes. |
| XLSX, XLSM | `xlsx_text` | Read-only `openpyxl`; preserves sheet names, row numbers, values, and formula text. Macros are never loaded or executed. |
| XLS | `xls_text` | Read-only `xlrd` for legacy binary workbooks. |
| DOCX | `docx_text` | Paragraphs, styles, tables, headers, footers, and bounded metadata via `python-docx`. |
| PPTX | `pptx_text` | Slide text, tables, and speaker notes via `python-pptx`. |
| ZIP | member extractors | Safely expands readable PDF, Office, and text members while preserving the archive filename, archive hash, and member path on every Mission input. |

OOXML packages are rejected when encrypted, malformed, excessively expanded, or composed of too many/oversized parts. Spreadsheet dimensions, presentation slide counts, source bytes, and extracted text bytes are all bounded before persistence.

ZIP ingestion is non-recursive. It rejects absolute/traversal paths, backslash paths, symlinks, encryption, duplicate member paths, abnormal compression ratios, more than 128 files, members over 100 MiB, or more than 256 MiB total expansion. Nested archives and unsupported executables are not extracted. A Mission may pin at most 32 readable members; only the first eight receive inline excerpts, while all pinned member refs remain available through canonical reads.

ZIP member names are decoded independently. Standards-compliant UTF-8 names are preserved; legacy entries without the UTF-8 flag are recovered from their raw CP437 projection using scored UTF-8 and GB18030 routes before falling back to CP437. This also repairs previously persisted mojibake names at Mission input and evidence projection boundaries without changing immutable file contents or hashes.

## Generated files

Mission code may write CSV, XLSX, DOCX, PPTX, or ZIP results under `/workspace/outputs`, register the file with `sandbox.register_artifact`, and freeze it through `artifact.create_candidate`. The candidate keeps the sealed Sandbox ref, content hash, MIME type, safe filename, and a bounded human-readable summary.

After stage acceptance and user review, `assets.create_from_preview` materializes the immutable bytes under `WORKSPACE_ASSET_ROOT/<workspace-id>/generated_files/<hash-prefix>/<hash>.<suffix>` and creates the canonical `workspace_assets` row with Mission review provenance. Mission Console exposes an authenticated download only after commit. Office packages are checked for valid package structure, unsafe paths, encryption, macros, ActiveX content, expansion limits, and CRC integrity before entering review storage.

## OfficeCLI decision

OfficeCLI is not part of the online upload/Mission ingestion path. Its built-in strengths are editing, semantic inspection, rendering, and visual QA for modern DOCX/XLSX/PPTX files; those formats already have deterministic native extractors here. Running a third-party binary during uploads would duplicate extraction and add process, update, and supply-chain surface.

If Wenjin later adds agent-authored Office editing or render-and-review workflows, OfficeCLI should be integrated as a pinned, no-network sandbox tool with `OFFICECLI_SKIP_UPDATE=1`, immutable input/output mounts, bounded stdout, and explicit tool-catalog/policy registration. It must not be invoked directly by Gateway request handlers.

Legacy DOC/PPT conversion, if required, belongs in a separate conversion worker or sandbox image rather than the main backend image.
