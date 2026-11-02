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
