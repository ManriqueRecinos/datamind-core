# AI Training, Continuous Learning & User Teaching Methodology Checklist: DataMind Core (`001-rag-core-service`)

**Purpose**: Validate the completeness, clarity, consistency, and measurability of requirements for teaching the AI (`datamind-core` & `datamind-studio`) — covering relational schema vectorization, conversational teaching in chat (`teach_knowledge`), explicit output mode detection (`wants_chart` vs `wants_table` vs `text_only`), custom business glossary/synonyms, Golden SQL few-shot learning, business formulas for charts, and the user's guided curriculum for training the AI.
**Created**: 2026-11-10
**Reviewed & Verified**: 2026-11-10 (`PASS: 17/17`)
**Feature**: [spec.md](../spec.md) | [plan.md](../plan.md) | [tasks.md](../tasks.md)

## Relational Schema & Foreign-Key Teaching Requirements

- [x] CHK001 - Are requirements explicitly defined for how the user must select and vectorize both sides of a relational boundary (e.g., master table `empresa`/`companies` and child table `usuario`/`users`) so `1-Hop` graph expansion in `pgvector` has complete target metadata? [Completeness, Spec §US7, §US8]
- [x] CHK002 - Is the requirement specified for how non-standard foreign keys (e.g., `users.current_company_id = companies.id` or `cod_cia` -> `compania.id_cia` that do not follow `id_<tabla>` or `FOREIGN KEY` constraints) can be manually taught by the user (via chat or UI) and persisted into `pgvector`? [Gap Resolved, Spec §US8.1, §US8.3]
- [x] CHK003 - Are database column comment extraction (`COLUMN_COMMENT` in MariaDB/MySQL and `col_description` in PostgreSQL) requirements defined so comments added in the DB engine are automatically embedded during table vectorization? [Completeness, Plan §Phase 16, Task T097]

## Conversational Teaching (`teach_knowledge`) & Output Mode Control (`wants_chart` / `wants_table`)

- [x] CHK004 - Are requirements defined so that when the user teaches a rule or relationship directly in the chat (e.g., *"La tabla users se relaciona con la tabla companies uniendo users.current_company_id= companies.id. Cuando el usuario pida datos o gráficos por empresa, nunca muestres current_company_id; haz siempre JOIN empresa y muestra empresa.name"*), the AI classifies it as `teach_knowledge`, stores the vector, and replies confirming what it learned **without** executing SQL or rendering charts/tables? [Critical Gap Resolved, Spec §US8.1, Task T098, T100]
- [x] CHK005 - Are requirements specified so that conditional mentions of `"gráficos"` or `"tablas"` inside a rule (*"cuando el usuario pida datos o gráficos..."*) do NOT falsely trigger `wants_chart = true` or `data_query`? [Clarity, Spec §US8.1, §US8.2, Task T098]
- [x] CHK006 - Are requirements defined for distinguishing when the user asks for **a Chart** (`wants_chart = true`), when the user asks for **a Table/List** (`wants_table = true`), and when the user only asks a **Question in Text** (`wants_chart = false, wants_table = false`) so the UI does not force tables and charts on every message? [Usability & Consistency, Spec §US8.2, Task T098, T101]

## Business Glossary, Synonyms & Status Code Translation Requirements

- [x] CHK007 - Are requirements defined for teaching the AI domain synonyms and business slang (e.g., *"Cuando el usuario diga 'rollo crudo', se refiere a `tipo_tela = 'CRUDO'` en la tabla `rollos`"*) so natural language queries translate into exact SQL filters? [Clarity, Spec §US8.3]
- [x] CHK008 - Is the requirement specified for mapping cryptic numeric/code statuses (e.g., `estado = 1` means `Activo`, `estado = 2` means `En Tejeduría`, `estado = 9` means `Anulado`) into human-readable `CASE WHEN` labels for charts and tables? [Completeness, Spec §US8.3]
- [x] CHK009 - Are requirements clear on whether business rules and dictionary terms taught by the user are retrieved during `data_query` intent (SQL & Chart generation) in addition to `process_qa` intent? [Consistency, Plan §Phase 16, Task T100]

## Golden SQL Few-Shot Learning & Metric Formula Requirements

- [x] CHK010 - Are requirements defined for allowing the user to teach "Golden SQL Examples" (Question + Verified `SELECT ... JOIN` Query) so the AI learns complex multi-table `JOIN` patterns by example (Few-Shot RAG)? [Completeness, Spec §US8.3]
- [x] CHK011 - Is validation specified for user-taught Golden SQL examples (e.g., enforcing read-only `SELECT` validation via `sqlglot` before storing a Golden SQL example in `pgvector`)? [Security, Spec §US4, §US8.3, Task T099]
- [x] CHK012 - Are requirements defined for teaching business formulas and KPIs (e.g., *"Eficiencia = `(metros_producidos / metros_programados) * 100`"* or *"Días de atraso = `DATEDIFF(fecha_entrega, fecha_compromiso)`"*) so the AI calculates derived metrics accurately in charts? [Clarity, Spec §US8.3]

## Interactive AI Training Center UI & Knowledge Lifecycle Requirements

- [x] CHK013 - Are UI requirements specified for a dedicated, easy-to-use "Centro de Entrenamiento IA" (`🎓 Entrenar IA`) where non-technical users can add, list, filter, and delete learned rules, custom relationships, and SQL examples without writing code? [Usability, Spec §US8.3, Task T101]
- [x] CHK014 - Are requirements defined for preventing duplicate or contradictory rules in `pgvector` when a user updates or re-teaches an existing business rule or table relationship? [Edge Case, Spec §US8.3, Task T099]
- [x] CHK015 - Is connection-scoping (`connection_id` metadata) specified for learned rules and Golden SQL examples so rules taught for Database A do not pollute SQL generation for Database B? [Consistency, Data Integrity, Spec §US8.1, §US8.3]

## User Learning Curriculum & Verification Methodology Requirements

- [x] CHK016 - Does the specification/plan include a structured, step-by-step learning curriculum (`Playbook de Entrenamiento`) that teaches the user *what* to teach the AI, *in what order*, and *how to write high-signal training rules*? [Completeness, Spec §US8.5, Tasks T103–T107]
- [x] CHK017 - Are measurable verification criteria and observability defined for the user to test whether the AI successfully learned a new rule or relationship (e.g., before/after prompt verification in the chat and viewing applied rules)? [Measurability & Observability, Spec §US8.4, Tasks T103–T107]
