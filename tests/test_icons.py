"""The mark, wherever something asks for one.

Three surfaces were asked for: the browser tab, a Google result, and a phone's
home screen. Each wants a different file in a different format, and the way
this fails is silently — a missing apple-touch-icon is a home screen showing a
grey screenshot of the page, which nobody reports as a bug.
"""

import json
import pathlib
import struct

import pytest
from fastapi.testclient import TestClient

from app.main import app

STATIC = pathlib.Path(__file__).parent.parent / "app" / "web" / "static"


@pytest.fixture
def client():
    return TestClient(app)


def test_every_icon_the_document_asks_for_exists(client):
    """A <link> pointing at nothing is worse than no <link>: the browser stops
    looking and shows the default."""
    html = client.get("/").text
    import re

    for href in re.findall(r'<link rel="(?:icon|apple-touch-icon|manifest)" href="([^"]+)"', html):
        path = href.split("?")[0]
        assert client.get(path).status_code == 200, href


def test_the_icon_is_also_at_the_root(client):
    """Crawlers ask for /favicon.ico without reading the page. Google is one."""
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.content[:4] == b"\x00\x00\x01\x00"  # ICO magic


def test_the_ico_carries_a_size_google_will_use(client):
    """Google wants a square favicon of at least 48px, or it draws its own."""
    data = client.get("/favicon.ico").content
    count = struct.unpack_from("<H", data, 4)[0]
    sizes = set()
    for n in range(count):
        width, height = struct.unpack_from("BB", data, 6 + n * 16)
        # 0 means 256 in the ICO header.
        sizes.add((width or 256, height or 256))
    assert (48, 48) in sizes or (64, 64) in sizes, sizes
    assert all(w == h for w, h in sizes), sizes


def test_the_apple_icon_is_the_size_ios_wants(client):
    from PIL import Image

    with Image.open(STATIC / "apple-touch-icon.png") as image:
        assert image.size == (180, 180)


def test_the_apple_icon_is_opaque():
    """iOS composites it on white. A transparent icon becomes a white slab with
    a ring floating in it."""
    from PIL import Image

    with Image.open(STATIC / "apple-touch-icon.png") as image:
        alpha = image.convert("RGBA").getchannel("A")
        assert alpha.getextrema() == (255, 255)


def test_the_manifest_is_valid_and_names_the_app(client):
    manifest = json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["name"] == "Offerly"
    assert manifest["start_url"] == "/"
    assert manifest["display"] == "standalone"


def test_the_manifest_offers_both_sizes_android_asks_for(client):
    manifest = json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes


def test_a_maskable_icon_is_offered():
    """Without one, Android shrinks the square inside its own shape and leaves
    a white border around it."""
    manifest = json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert any("maskable" in icon.get("purpose", "") for icon in manifest["icons"])


def test_every_manifest_icon_resolves(client):
    manifest = json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))
    for icon in manifest["icons"]:
        assert client.get(icon["src"]).status_code == 200, icon["src"]


def test_the_maskable_mark_stays_inside_the_safe_zone():
    """Android may crop to a circle of 80% of the width. Anything outside that
    is not guaranteed to survive, so the mark has to sit well within it."""
    from PIL import Image

    with Image.open(STATIC / "icon-512-maskable.png") as image:
        pixels = image.convert("RGBA")
        width, height = pixels.size
        mark = [
            (x, y)
            for x in range(0, width, 4)
            for y in range(0, height, 4)
            if pixels.getpixel((x, y))[:3] != (22, 24, 38)
        ]

    assert mark, "the mark is missing entirely"
    centre = width / 2
    furthest = max(((x - centre) ** 2 + (y - centre) ** 2) ** 0.5 for x, y in mark)
    assert furthest <= width * 0.40, f"mark reaches {furthest / width:.0%} of the width"


def test_the_page_still_fetches_nothing_from_anyone_else(client):
    """Icons are the usual excuse for a CDN. Not here."""
    import re

    html = client.get("/").text
    hosts = {
        host
        for host in re.findall(r'(?:src|href)\s*=\s*"(?:https?:)?//([^/"]+)', html)
        if host != "testserver"
    }
    assert hosts <= {"github.com"}, hosts


# ── the social avatar ────────────────────────────────────────────────

BRAND = pathlib.Path(__file__).parent.parent / "brand"


def test_the_avatar_is_square_and_large_enough_to_upload():
    from PIL import Image

    with Image.open(BRAND / "offerly-avatar-1080.png") as image:
        assert image.size == (1080, 1080)


def test_the_avatar_is_opaque_to_the_corners():
    """It is cropped to a circle by the platform. A transparent corner is a
    corner the crop cannot land on cleanly."""
    from PIL import Image

    with Image.open(BRAND / "offerly-avatar-1080.png") as image:
        assert image.convert("RGBA").getchannel("A").getextrema() == (255, 255)


def test_the_avatar_survives_a_circular_crop():
    """Everything that matters has to sit inside the inscribed circle, because
    that is all Instagram keeps."""
    from PIL import Image

    with Image.open(BRAND / "offerly-avatar-1080.png") as image:
        pixels = image.convert("RGBA")
        width, _ = pixels.size
        mark = [
            (x, y)
            for x in range(0, width, 6)
            for y in range(0, width, 6)
            if pixels.getpixel((x, y))[:3] != (22, 24, 38)
        ]

    assert mark, "the mark is missing entirely"
    centre = width / 2
    furthest = max(((x - centre) ** 2 + (y - centre) ** 2) ** 0.5 for x, y in mark)
    # The inscribed circle has radius width/2; nothing may reach it.
    assert furthest < centre * 0.95, f"the mark reaches {furthest / centre:.0%} of the crop radius"
