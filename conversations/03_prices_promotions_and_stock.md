# Prices, active promotions and unavailable products

> Promotional price shown with original price and percentage; no Black Friday promise; out-of-stock alternatives.

- Model: `openai/gpt-6-luna`
- Recorded at: 2026-11-04 00:24

---

**Cliente:** Quanto custa o Takamine GD20?

*Tools: `search_products({'query': 'Takamine GD20', 'category': 'Violões', 'max_price': 0, 'available_only': False})`, `get_product({'product_id': 95})`*

**Mel:** O Takamine GD20 custa **R$ 2.199,00**. No PIX, fica **R$ 2.089,05**; no cartão, em até **12x de R$ 183,25 sem juros**.

O time humano volta amanhã, quarta-feira (04/11), às 09:00.

---

**Cliente:** E o ukulele Ohana CK-20, está em promoção?

*Tools: `search_products({'query': 'Ohana CK-20', 'category': 'Ukuleles', 'max_price': 0, 'available_only': False})`, `get_product({'product_id': 121})`*

**Mel:** Sim! O Ohana CK-20 está com **20% de desconto**: de **R$ 549,00** por **R$ 439,20**. O preço no PIX também é **R$ 439,20**; no cartão, até **5x de R$ 87,84 sem juros**.

---

**Cliente:** Vai ter desconto de Black Friday no Takamine?

*Tools: `get_policy({'section': 'promotions'})`, `get_product({'product_id': 95})`*

**Mel:** Ainda não dá pra confirmar desconto de Black Friday no Takamine GD20. No momento, não consta promoção ativa para ele; o preço está em **R$ 2.199,00** (ou **R$ 2.089,05 no PIX**). Só posso confirmar um desconto quando ele aparecer como ativo no sistema.

---

**Cliente:** Vocês têm o Giannini GF-3D?

*Tools: `search_products({'query': 'Giannini GF-3D', 'category': 'Violões', 'max_price': 0, 'available_only': True})`, `get_product({'product_id': 96})`*

**Mel:** No momento, o **Giannini GF-3D está sem estoque**. Como opções disponíveis, temos o **Shelby SGD-195E**, o **Yamaha C70** e o **Tagima Dallas Tuner**. Quer que eu te ajude a escolher entre eles?

---
