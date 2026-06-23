---
graph: false
id: raw_source_registry_readme
title: Raw Source Registry
status: active
---

# Source Registry

Store source metadata here before creating or updating `wiki/sources/` cards.

Recommended fields:

```yaml
id: source_unique_id
title: Source Title
source_type: official_spec | vendor_app_note | book | paper | web_article | internal_note
source_tier: tier_0 | tier_1 | tier_2 | tier_3
version: null
path_or_url: null
access: local_only | public_url | user_provided | internal
allowed_usage:
  - compliance_limit
  - design_rule
  - background
notes: ""
```

Do not commit local-only documents themselves unless redistribution rights are
explicit.
