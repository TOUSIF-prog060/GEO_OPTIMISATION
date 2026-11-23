# Reference data

Versioned inputs. **Never edit a version after a run has used it**: copy it to the next version.
Every row must come from a real, checkable source. Do not guess values.

| File | Used by | Rows |
|---|---|---|
| `prompt_panel_<v>.csv` | Discovery | shopper questions |
| `domains_<v>.csv` | Diagnostics | website → type (brand_owned, competitor, retailer, editorial, ugc, video, other) |
| `products_<v>.csv` | Diagnostics (product mentions) | products to track |
| `reference_facts_<v>.csv` | Diagnostics (accuracy checks) | verified facts about brands/products |

## products_<v>.csv
| column | example | notes |
|---|---|---|
| product_id | `SUN-NEU-UDL50` | stable, unique |
| product_name | Ultra Sheer Dry-Touch Sunscreen SPF 50+ | |
| maker | Neutrogena | manufacturer |
| aliases | `Ultra Sheer Dry Touch\|Neutrogena Ultra Sheer` | `\|`-separated; whole-word matched |
| category | sunscreen | same names as the prompt panel |
| source_url | product page used to verify | required |
| last_verified_at | 2026-11-23 | ISO date, required |

## reference_facts_<v>.csv
| column | example | notes |
|---|---|---|
| fact_id | `F-SEPH-001` | stable, unique |
| subject_type | `brand` or `product` | |
| subject | `Sephora India` or a product_id | brand name must match the config |
| attribute | `offers_cash_on_delivery`, `spf`, `price_inr` | snake_case |
| approved_value | `true`, `50`, `1099` | the verified value |
| value_type | `boolean`, `number`, `text` | |
| tolerance | `0.10` | numbers only: allowed relative difference (e.g. prices) |
| source_url | page where it was verified | required |
| last_verified_at | 2026-11-23 | required |

Accuracy verdicts: **match**, **mismatch**, **not_mentioned** (the answer doesn't state it), **unverifiable** (stated, but can't be compared, e.g. vague text). Accuracy rate = match / (match + mismatch).
