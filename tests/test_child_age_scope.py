from unittest.mock import patch

import pytest

from auth.child_provisioning import MAX_CHILD_AGE, MIN_CHILD_AGE, create_child_for_verified_parent


@pytest.mark.parametrize("age", [MIN_CHILD_AGE - 1, MAX_CHILD_AGE + 1])
def test_new_child_account_rejects_age_outside_final_scope(age):
    parent = {"user_id": 1, "full_name": "Parent", "email": "parent@example.test"}
    with patch("auth.child_provisioning.fetch_one", side_effect=[parent, None]):
        with pytest.raises(ValueError, match="between 6 and 16"):
            create_child_for_verified_parent(
                1,
                {
                    "username": "safe_child",
                    "full_name": "Safe Child",
                    "age": age,
                    "password": "strong-pass-1",
                },
            )


def test_final_child_age_constants_are_6_to_16():
    assert (MIN_CHILD_AGE, MAX_CHILD_AGE) == (6, 16)
