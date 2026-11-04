# Behavioral evaluation report

- Model: `openai/gpt-6-luna`
- Run at: 2026-11-04 00:10
- Result: **0/1 passed, 1 failed, 0 provider errors**

LLM output is non-deterministic: this is a sample run, not a guarantee. Checks are regex-based and accent-insensitive; tool checks use the agent's tool trace. ⚠️ marks provider errors (quota, outage), which say nothing about the agent's behavior.

| Scenario | Description | Result | Tools used |
|---|---|---|---|
| `price_lookup` | Price of a specific product with PIX discount and installments | ❌ | `search_products({'query': 'Takamine GD20', 'category': 'Violões', 'max_price': 1, 'available_only': False})`, `search_products({'query': 'Takamine GD20', 'category': 'Violões', 'max_price': 999999, 'available_only': False})`, `get_policy({'section': 'opening_hours'})` |

## Failures and errors

### `price_lookup`

- expected tool get_product to be called
- reply should match /2\.089,05/

Reply:

> O Takamine GD20 Dreadnought Natural está por **R$ 2.199,00**. 😊
> 
> A equipe volta amanhã, quarta-feira, às 9h.

