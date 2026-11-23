# Knowledge base (approved brand documents)

The Content Copilot only writes from what is in this folder. Add one Markdown file per
approved source, for example the Sephora India FAQ, delivery/returns policy, a category page or
a brand list. **Copy text from the real public page; do not write or guess facts.**

Each file needs a front-matter header:

```markdown
---
title: Sephora India: Shipping & Delivery FAQ
source_url: https://www.sephora.in/...
verified_at: 2026-11-23
---
(text copied from the page)
```

Then run `python scripts/ingest_knowledge.py` (needs OPENAI_API_KEY for embeddings).
Files whose text has not changed are skipped. This README is ignored.
