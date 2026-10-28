"""Media type per file (M2): captures are WebM/Matroska, renders MP4."""

from media_api import media_type_for


def test_media_type_follows_the_file_extension():
    assert media_type_for("s3://bucket/renders/a-landscape.mp4") == "video/mp4"
    assert media_type_for("local://captures/x/page@abc.webm") == "video/webm"
    assert media_type_for("captures/x/capture.MKV") == "video/x-matroska"
    assert media_type_for("weird/no-extension") == "video/mp4"
