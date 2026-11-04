# Reducing cyclomatic complexity: patterns by cause

Every decision structure (`if`, `elif`, `for`, `while`, `and`, `or`, `except`, comprehension with `if`, ternary,
`assert`, `case`) adds +1 to CC. Lowering the number is a consequence of removing a decision, not of hiding it in
another function.

---

## 1. Guard clauses instead of nesting
Nesting does not add more CC than a flat `if`, but each level invites more branches. Invert and return early.

```python
# Before
def process(order):
    if order is not None:
        if order.status == "pending":
            if order.customer.verified:
                return confirm(order)
            else:
                return reject(order)
        else:
            return None
    return None

# After — same behavior, each condition isolated
def process(order):
    if order is None or order.status != "pending":
        return None
    if not order.customer.verified:
        return reject(order)
    return confirm(order)
```

---

## 2. Dictionary dispatch instead of a long `if/elif`
Chains over a discrete value (event type, status, provider) become a table. The dispatcher drops to CC ~2 and each
handler is testable on its own.

```python
HANDLERS = {"confirmed": handle_confirmed, "overdue": handle_overdue, "refunded": handle_refunded}

def handle(event):
    handler = HANDLERS.get(event.type)
    if handler is None:
        logger.warning("unhandled event: %s", event.type)
        return
    handler(event)
```

---

## 3. Chained validations → list of rules

```python
RULES = [
    (lambda r: bool(r.query or r.category), "query or category required"),
    (lambda r: r.max_price is None or r.max_price > 0, "max_price must be positive"),
]

def validate(request):
    for check, message in RULES:
        if not check(request):
            raise ValueError(message)
```

---

## 4. Compound boolean conditions → named predicate
`and`/`or` add to CC and hide intent.

```python
# Before — CC +3 in one line
if product.status == "active" and product.stock > 0 and not product.discontinued:
    ...

# After — the condition gets a name and is tested directly
def is_purchasable(product) -> bool:
    return product.status == "active" and product.stock > 0 and not product.discontinued
```

The total CC does not vanish — it moves to where it is cohesive and easy to test.

---

## 5. Broad `try/except` → minimal scope
Each `except` adds +1, and a `try` around 40 lines with five handlers also hides which line failed. Protect only
the call that can fail in that way, in its own small function.

---

## 6. Fat HTTP handlers → service layer
A handler that validates, queries, decides, writes and formats is the usual rank D/E. Keep the handler thin
(parse input, call a service, map the result to a response) and put the decision in a service that runs without
an HTTP request and is testable without a client.

---

## 7. Loops with filters → a pipeline of small predicates (or SQL)
A loop that applies several `if ...: continue` filters accumulates one decision per filter. Turn each filter into a
named predicate and compose them, or push the filtering to the database when the data lives there.

```python
FILTERS = [matches_terms, in_category, within_budget, purchasable]
results = [p for p in products if all(f(p, request) for f in FILTERS)]
```

---

## When **not** to refactor
- **Protocol dispatchers** already shaped as a table, where the remaining `if` is the fallback.
- **Parsers/state machines** whose complexity is intrinsic to the format; invest in edge-case tests instead.
- **Declarative configuration** (settings, mappings).

When a block is legitimately complex, document why in a short comment and cover its paths with tests. A justified,
tested rank D beats six single-use helpers scattered across the module.
