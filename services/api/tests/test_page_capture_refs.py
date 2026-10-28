"""Page-capture image refs (review fix): only this capture's storage key."""

from storyboard_api import expected_image_ref_ok

OFFER, CAP = "o-1", "c-1"


def test_only_the_managed_key_of_this_capture_is_accepted():
    assert expected_image_ref_ok("local://pages/o-1/c-1.png", OFFER, CAP)
    assert expected_image_ref_ok("s3://media/pages/o-1/c-1.png", OFFER, CAP)
    for hostile in ("/app/.env", "C:/repo/.env", "local://pages/o-2/c-1.png",
                    "local://pages/o-1/c-1.png/../../x", "s3://media/other/pages/o-1/c-1.png",
                    "s3:///pages/o-1/c-1.png", "https://evil/pages/o-1/c-1.png", ""):
        assert not expected_image_ref_ok(hostile, OFFER, CAP), hostile
