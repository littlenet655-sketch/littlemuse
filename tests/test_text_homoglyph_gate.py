"""Regression tests: Unicode homoglyph bypass of the deterministic text gate.

Adversarial finding: Cyrillic/Greek lookalikes (е/а/і/...) survive NFKC and
evaded the sexual / grooming / self-harm term lists -- e.g. "send nudеs"
(Cyrillic е U+0435) scored clean. _normalized_text now folds confusables to
Latin before matching; the original text passed to ML/audit is untouched.

No Postgres / torch / network required.
"""
import pytest

from safety import text_service
from safety.text_service import _normalized_text, check_text_deterministic

CYR_E = "\u0435"  # Cyrillic small letter ie (looks like e)
CYR_A = "\u0430"  # Cyrillic small letter a (looks like a)
CYR_I = "\u0456"  # Cyrillic small letter byelorussian-ukrainian i (looks like i)
GRK_E = "\u03b5"  # Greek small letter epsilon (looks like e)


@pytest.mark.parametrize(
    "adversarial,category",
    [
        ("send nud" + CYR_E + "s", "SEXUAL_LANGUAGE"),
        ("send n" + CYR_A + "ked pic", "SEXUAL_LANGUAGE"),
        ("s" + CYR_E + "nd nudes", "SEXUAL_LANGUAGE"),
        ("s" + GRK_E + "nd nudes", "SEXUAL_LANGUAGE"),
        ("don't tell your p" + CYR_A + "rents", "GROOMING"),
        (CYR_I + " want to die", "SELF_HARM"),
        ("kill yours" + CYR_E + "lf", "CYBERBULLYING"),
    ],
)
def test_homoglyph_evasions_are_caught(adversarial, category):
    result = check_text_deterministic(adversarial)
    assert result["category"] == category, f"{adversarial!r} scored {result['category']}"


def test_homoglyph_folds_to_plain_latin_before_matching():
    assert _normalized_text("send nud" + CYR_E + "s") == "send nudes"


def test_original_text_not_mutated_for_ml_audit():
    # The fold applies only to the normalized copy; callers still hold the
    # original string for ML scoring and audit trails.
    original = "send nud" + CYR_E + "s"
    check_text_deterministic(original)
    assert CYR_E in original


@pytest.mark.parametrize("benign", ["My science fair project", "i am ok", "hello friend"])
def test_benign_text_stays_clean(benign):
    assert check_text_deterministic(benign)["category"] == "TEXT"
