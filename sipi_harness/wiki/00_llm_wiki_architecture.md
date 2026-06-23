---
graph: false
kind: hub_page
id: wiki_architecture
topic: wiki_architecture
summary: "The LLM wiki is the design-knowledge layer: SI, PI, package/PCB, and verification strategy concepts connected by relationships."
concepts:
  - LLM Wiki
  - Knowledge Intake
  - Web Research
  - User Reference
  - Wiki Fusion
  - Design Strategy
  - Signal Integrity
  - Power Integrity
  - Package
  - PCB
  - Verification Strategy
  - Evidence
claims:
  - "The wiki should store design knowledge, not transient tool execution logs."
  - "For a new design request, the wiki strategy should be built from web research, user-provided references, and reusable wiki pages."
  - "Web research contributes current design practice; user references contribute governing requirements, figures, tables, equations, and trusted local context."
  - "Toolchain flow belongs in CODEX.md, README_AGENT.md, and skills."
  - "The graph should make major categories visible: Signal Integrity, Power Integrity, Package/PCB, and Verification Strategy."
relationships:
  - "Knowledge Intake|collects|Web Research"
  - "Knowledge Intake|collects|User Reference"
  - "Web Research|feeds|Wiki Fusion"
  - "User Reference|feeds|Wiki Fusion"
  - "LLM Wiki|feeds|Wiki Fusion"
  - "Wiki Fusion|generates|Design Strategy"
  - "LLM Wiki|organizes|Design Strategy"
  - "Design Strategy|covers|Signal Integrity"
  - "Design Strategy|covers|Power Integrity"
  - "Design Strategy|covers|Package"
  - "Design Strategy|covers|PCB"
  - "Design Strategy|drives|Verification Strategy"
  - "Evidence|supports|Design Strategy"
---

# LLM Wiki Architecture

The LLM wiki is the reusable design-knowledge layer. It should help an agent or
engineer build a design strategy from SI/PI principles, package/PCB constraints,
spec evidence, web research, user references, and verification methods.

For each new design request, the knowledge input should be:

```text
Web Research + User References + Existing LLM Wiki -> Wiki Fusion -> Design Strategy
```

Web research captures current public design strategy and verification practice.
User references capture user-approved specs, books, datasheets, figures, tables,
pin maps, masks, loading models, and local context. The design strategy should
cite both streams when they affect geometry, stackup, solver setup, or pass/fail
checks.

Tool execution details belong outside the wiki:

- `CODEX.md`: startup flow and hard rules for agents.
- `README_AGENT.md`: detailed handoff and completion contract.
- `.codex/skills/`: tool-specific operating procedures.
- `outputs/<case>/`: case-specific manifests, reports, solver files, and logs.

## Graph Categories

```text
LLM Wiki
  -> Knowledge Intake
     -> Web Research
     -> User Reference
     -> Wiki Fusion
  -> Signal Integrity
     -> Impedance / Loss / Crosstalk / Return Path / Eye
  -> Power Integrity
     -> PDN / IR Drop / SSN / Decoupling / Rail Noise
  -> Package and PCB
     -> Stackup / Launch / Via / Pad / Length Matching
  -> Verification Strategy
     -> EM Extraction / Touchstone / ADS / Reports
```

Every wiki page should provide concepts and relationships that strengthen this
taxonomy rather than floating as an isolated document.

## Typed Card Entry Points

- [[Schema]]
- [[Index]]
- interface profile cards selected by the active request
- spec constraint cards selected from reviewed tier-0 evidence
- design rule cards selected by routing, stackup, SI, PI, and validation topics
- validation metric and flow cards selected by required benchmark methods

## Adopted LLM Wiki Practices

This harness adopts the parts of the LLM Wiki pattern that directly improve
spec-driven SI/PI work:

- Raw/user/web sources remain separate from generated wiki pages.
- `purpose.md` defines why the wiki exists and what questions it should answer.
- `schema.md` defines page frontmatter, relationship, and traceability rules.
- `index.md` is the content catalog for agent navigation.
- `overview.md` summarizes current graph health and topic coverage.
- `log.md` is the chronological operation record.
- Knowledge intake uses SHA256 state and an ingest queue scaffold so unchanged
  sources can be skipped and failed ingest work can be retried.
- Graph output includes relevance-signal metadata and graph insights for
  isolated concepts, bridge concepts, and sparse communities.
- `lint:wiki` is the health check for missing metadata, broken wikilinks, and
  source-traceability gaps.

Not adopted by default:

- A full desktop app runtime.
- Always-on file watching.
- Vector database or embedding search.
- External web-search provider APIs.

Those are optional future integrations. The current harness keeps the wiki
filesystem-native, auditable, and close to the EDA workflow.
