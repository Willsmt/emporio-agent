# Behavioral evaluation report

- Model: `openai/gpt-6-luna`
- Run at: 2026-11-04 00:07
- Result: **0/1 passed, 1 failed, 0 provider errors**

LLM output is non-deterministic: this is a sample run, not a guarantee. Checks are regex-based and accent-insensitive; tool checks use the agent's tool trace. ⚠️ marks provider errors (quota, outage), which say nothing about the agent's behavior.

| Scenario | Description | Result | Tools used |
|---|---|---|---|
| `price_lookup` | Price of a specific product with PIX discount and installments | ❌ | `search_products({'query': 'Takamine GD20', 'category': 'Violões', 'max_price': 0, 'available_only': False})`, `search_products({'query': 'Takamine', 'category': 'Violões', 'max_price': 0, 'available_only': False})` |

## Failures and errors

### `price_lookup`

- expected tool get_product to be called
- reply should match /2\.199,00/
- reply should match /2\.089,05/

Reply:

> Não encontrei o Takamine GD20 no catálogo, então não consigo confirmar o preço. A loja está fechada agora e a equipe volta amanhã, quarta-feira, às 9h. Se quiser, posso procurar outro violão pra você.

