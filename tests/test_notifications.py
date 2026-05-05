from skoleintra.db.models import Item
from skoleintra.notifications.dispatcher import _ntfy_markdown_for, _subject_for


def test_photo_album_notifications_use_domain_label():
    item = Item(
        type="photo_album",
        title="Photo album: Classroom week 19",
        sender="Teacher Example",
        body_html="<p>Classroom week 19</p><p>Photos: 2</p><p>Outdoor crafts.</p>",
    )

    assert (
        _subject_for(item) == "[Skoleintra:photo album] Photo album: Classroom week 19"
    )
    assert _ntfy_markdown_for(item).splitlines()[:2] == [
        "**Photo album: Classroom week 19**",
        "`photo album` • Teacher Example",
    ]
