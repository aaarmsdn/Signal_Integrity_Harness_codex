# User Reference Registry

Put user-provided or user-approved source documents for local processing here
only when they are safe to keep in the workspace. Most PDFs/books/specs should
remain local and uncommitted.

Case-specific references should normally be copied or linked under:

```text
outputs/<case>/knowledge_intake/user_references/
```

The repo-level `wiki/raw/datasheet/` directory can be used as a local source library for
approved specifications. Register the path in the case registry or config, but
keep the PDF itself untracked unless redistribution rights are explicit.

Register references with metadata rather than relying on hidden session state:

```json
{
  "kind": "user_reference_registry",
  "references": [
    {
      "id": "reference_id",
      "title": "Reference title",
      "path": "local/path/or/original/location.pdf",
      "topic": "specification",
      "summary": "What this reference controls.",
      "concepts": ["Ball Map", "Eye Mask"],
      "claims": ["Short extracted/paraphrased requirement."],
      "evidence": [
        {
          "page": 10,
          "figure": "Figure X-Y",
          "table": "Table X-Y",
          "artifact": "spec_evidence/page10.png"
        }
      ]
    }
  ]
}
```

When a design rule, pin map, loading model, or mask comes from a user reference,
the case strategy must cite the page/figure/table evidence.
