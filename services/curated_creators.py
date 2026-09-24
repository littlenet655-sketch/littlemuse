from __future__ import annotations

# Editorial personas are product-owned identities, never child/user accounts.
# creator_key is persisted on curated_content; this dictionary is the
# low-latency rendering contract mirrored by the migration seed rows.
CURATED_CREATORS = {
    "ananya_explores": {"display_name": "Ananya Explorer", "username": "ananya_explores"},
    "aarav_cooking": {"display_name": "Chef Aarav", "username": "aarav_cooking"},
    "kabir_sports": {"display_name": "Kabir Champion", "username": "kabir_sports"},
    "maya_astronomy": {"display_name": "Maya Sharma", "username": "maya_astronomy"},
    "sam_origami": {"display_name": "Samantha Rao", "username": "sam_origami"},
    "leo_robotics": {"display_name": "Leo D'Souza", "username": "leo_robotics"},
    "ait_star_student": {"display_name": "AIT Star Student", "username": "ait_star_student"},
    "real_kid_alpha": {"display_name": "Real Kid Alpha", "username": "real_kid_alpha"},
    "tagkid": {"display_name": "Tag Kid", "username": "tagkid"},
    "prockid": {"display_name": "Proc Kid", "username": "prockid"},
    "statuskid": {"display_name": "Status Kid", "username": "statuskid"},
    "kid_hbndif": {"display_name": "Little Kid", "username": "kid_hbndif"},
    "kid_wpzaxm": {"display_name": "Little Kid", "username": "kid_wpzaxm"},
    "hkid_14": {"display_name": "hkid_14 Name", "username": "hkid_14"},
}
DEFAULT_CURATED_CREATOR_KEY = "ait_star_student"


def creator_payload(creator_key: str | None) -> dict[str, str]:
    key = str(creator_key or DEFAULT_CURATED_CREATOR_KEY)
    if key not in CURATED_CREATORS:
        key = DEFAULT_CURATED_CREATOR_KEY
    row = CURATED_CREATORS[key]
    return {"creator_key": key, **row}
