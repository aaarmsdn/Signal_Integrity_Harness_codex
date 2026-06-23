# Web Research Registry

Store curated summaries of online design-strategy sources here when they are
reusable across cases. Case-specific web research should normally stay under
`outputs/<case>/knowledge_intake/web_research/`.

Each JSON registry may contain:

```json
{
  "kind": "web_research_registry",
  "sources": [
    {
      "id": "source_id",
      "title": "Source title",
      "url": "https://example.com/source",
      "publisher": "Publisher",
      "topic": "signal_integrity",
      "summary": "Short source summary.",
      "concepts": ["Crosstalk", "Return Path"],
      "claims": ["Short paraphrased reusable claim."],
      "design_rules": ["Actionable design rule."],
      "verification_methods": ["How to verify the rule."],
      "relationships": [["Crosstalk", "is reduced by", "Spacing"]]
    }
  ]
}
```

Do not store long copied article text. Store source metadata, paraphrased
claims, design implications, and links.
