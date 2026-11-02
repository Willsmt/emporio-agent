from emporio.text import digits_only, normalize


def test_normalize_removes_accents_case_and_extra_spaces():
    assert normalize("  Violão   Clássico ") == "violao classico"


def test_digits_only():
    assert digits_only("(67) 99812-3456") == "67998123456"
