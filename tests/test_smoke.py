from emporio.config import RAW_DIR

EXPECTED_RAW_FILES = [
    "desafio_tecnico_ai_eng - products.csv",
    "desafio_tecnico_ai_eng - categories.csv",
    "desafio_tecnico_ai_eng - customers.csv",
    "desafio_tecnico_ai_eng - orders.csv",
    "desafio_tecnico_ai_eng - order_items.csv",
    "desafio_tecnico_ai_eng - promotions.csv",
    "políticas_da_loja.pdf",
]


def test_raw_files_present():
    missing = [name for name in EXPECTED_RAW_FILES if not (RAW_DIR / name).exists()]
    assert not missing, f"Missing raw files: {missing}"
