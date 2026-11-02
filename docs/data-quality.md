# Data Quality Report

Issues found in the raw data provided by the store and how each one was handled.
Raw files in `data/raw/` are never modified; all handling happens in `src/emporio/data/etl.py`
(data issues) or in the tools layer (business rules).

| # | Finding | Handling | Where |
|---|---------|----------|-------|
| 1 | Customers 11 and 43 share the same email (`bruno.martins@jmail.com`) with different phones | Deduplicated by email, keeping the record referenced by orders (11). Logged as a warning. Customer 43's phone is lost (known limitation). | ETL |
| 2 | Orders 3 and 20 totals differ from current product prices (R$3,450 vs R$3,498; R$1,400 vs R$1,488) | Kept as-is: an order total is a snapshot of the price at purchase time. | ETL (no change) |
| 3 | Product 136 is `discontinued` but has 13 units in stock | Treated as not available for sale (policy 7.3). | Tools |
| 4 | Product 130 is `coming_soon` with 2 units in stock | Treated as not yet available for sale. | Tools |
| 5 | Product 96 is `active` with zero stock | Reported as out of stock; similar alternatives suggested (policy 7.3). | Tools |
| 6 | Categories 6, 7 and 8 (wind and orchestral strings) have no products, although the policy manual says the store sells them | The agent states these items are not currently available instead of inventing products. | Tools / prompt |
| 7 | Products 93, 96 and 99 have more than one promotion record | Valid (only expired ones overlap). Enforced at most one active promotion per product via a partial unique index. | ETL / schema |

## Policy manual (`políticas_da_loja.pdf`)

The manual was converted once into `data/curated/store_policies.md`. Contradictions and gaps are
resolved inside that file as visible "Esclarecimento" (clarification) blocks, so the agent reads
the rule and its interpretation together. The original PDF is untouched.

| ID | Finding | Assumption |
|----|---------|------------|
| A1 | Two phone numbers: (67) 3341-4444 (cover, §1.2) vs (67) 3321-4500 (§7) | (67) 3341-4444 is official: it appears twice, including the company registration table. |
| A2 | Email spelled with an accent in §1.2 (`empóriodamusica`) | `contato@emporiodamusica.com.br`, as on the cover; the accent is treated as a typo. |
| A3 | Manual mentions wind and orchestral string instruments; the catalog has none | Never claim availability without querying the system. |
| A4 | Minimum installment R$100 (§3 table) vs tiered rules (§3.1) | The more specific rule (§3.1) prevails: up to 3x R$50, 4–6x R$80, 7–12x R$100. |
| A5 | Shipping to other cities depends on ZIP code, weight and dimensions, which the system lacks | Inform carriers and delivery times; the cost is calculated at checkout. |
| A6 | Campaign discount ranges (§6.1), including Black Friday in November | Ranges describe campaigns in general; only promotions active in the system apply. |
| A7 | "Suggest partner stores" but none are listed | Never invent partner store names. |
