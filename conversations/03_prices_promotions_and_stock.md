# Prices, active promotions and unavailable products

> Promotional price shown with original price and percentage; no Black Friday promise; out-of-stock alternatives.

- Model: `openai/gpt-6-luna`
- Recorded at: 2026-11-04 01:07

---

**Cliente:** Quanto custa o Takamine GD20?

*Tools: `search_products({'query': 'Takamine GD20', 'category': 'Violões', 'max_price': 0, 'available_only': False})`, `get_product({'product_id': 95})`, `get_policy({'section': 'opening_hours'})`*

**Mel:** O Takamine GD20 Dreadnought Natural custa **R$ 2.199,00**. No PIX, fica **R$ 2.089,05**; no cartão, até **12x de R$ 183,25 sem juros**.

A loja abre hoje, quarta-feira (04/11), às 09:00.

---

**Cliente:** E o ukulele Ohana CK-20, está em promoção?

*Tools: `search_products({'query': 'Ohana CK-20', 'category': 'Ukuleles', 'max_price': 0, 'available_only': False})`, `get_product({'product_id': 121})`*

**Mel:** Sim! O Ohana CK-20 está com **20% de desconto**: de **R$ 549,00** por **R$ 439,20**. O valor no PIX é o mesmo, e no cartão dá para parcelar em até **5x de R$ 87,84 sem juros**.

---

**Cliente:** Vai ter desconto de Black Friday no Takamine?

*Tools: `get_policy({'section': 'promotions'})`, `search_products({'query': 'Takamine GD20', 'category': 'Violões', 'max_price': 0, 'available_only': False})`*

**Mel:** Ainda não consigo confirmar um desconto de Black Friday para o Takamine GD20. No momento, não há promoção ativa cadastrada para ele. Se entrar na campanha, a loja poderá confirmar o desconto quando estiver ativo.

---

**Cliente:** Vocês têm o Giannini GF-3D?

*Tools: `search_products({'query': 'Giannini GF-3D', 'category': 'Violões', 'max_price': 0, 'available_only': True})`, `get_product({'product_id': 96})`*

**Mel:** No momento, o **Giannini GF-3D Dreadnought Sunburst está esgotado**. Como alternativas disponíveis, encontrei:

- **Shelby SGD-195E Elétrico Aço Sunburst** — R$ 799,00  
- **Yamaha C70 Nylon Natural** — R$ 849,00  
- **Tagima Dallas Tuner Aço Natural** — R$ 749,00

Quer que eu te passe mais detalhes de algum deles?

---
