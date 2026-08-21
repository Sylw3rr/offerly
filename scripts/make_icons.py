"""Draw the app icons from the brand mark.

Build-time only. Pillow is not a dependency of the application — the files this
writes are committed, and the server only ever serves them. Run it when the
mark changes:

    pip install Pillow
    python scripts/make_icons.py

The mark is the ring from `_icons.html`: two circles with the inner one pushed
right, so the ring is heavy on the left and light on the right. In the SVG's
24-unit box the outer circle is centred (12, 12) with r 8.75 and the inner is
centred (13.35, 12.05) with r 6.5, which leaves the light side 0.9 units wide.

That last number is the whole difficulty. Nine tenths of a unit is about half a
pixel on a 16px favicon: the thin side of the ring would alias away and the
mark would read as a lopsided blob. So below a certain size the inner circle is
shrunk until the light side survives — the mark keeps its off-centre character
and stops pretending to a delicacy the pixels cannot hold.
"""

from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "web" / "static"
# Artwork for places outside the product: social profiles, a press kit.
BRAND = ROOT / "brand"

BG = (22, 24, 38, 255)  # --bg   #161826
MARK = (181, 171, 252, 255)  # --a-400 #b5abfc, the accent brightened to hold at 16px

# The mark, in the SVG's 24-unit box.
OUTER_C, OUTER_R = (12.0, 12.0), 8.75
INNER_C, INNER_R = (13.35, 12.05), 6.5

# Anti-aliasing: draw large, then resample down.
SUPER = 8

# Below this the light side of the ring stops being a shape and starts being an
# artefact. Measured on the finished image, not the supersampled one.
MIN_LIGHT_SIDE_PX = 1.3


def _inner_radius_for(mark_px: float) -> float:
    """The inner radius to use so the ring's light side stays visible.

    The light side measures `outer_r - inner_r - offset` in mark units. Solving
    that for the smallest inner radius that clears the floor is what keeps a
    16px icon from losing half its ring.
    """
    offset = ((INNER_C[0] - OUTER_C[0]) ** 2 + (INNER_C[1] - OUTER_C[1]) ** 2) ** 0.5
    units_per_px = (OUTER_R * 2) / mark_px
    floor_units = MIN_LIGHT_SIDE_PX * units_per_px

    light_side = OUTER_R - INNER_R - offset
    if light_side >= floor_units:
        return INNER_R
    return max(OUTER_R * 0.35, OUTER_R - offset - floor_units)


def draw_icon(size: int, *, mark_fraction: float, radius_fraction: float) -> Image.Image:
    """One square icon: the tile, then the ring punched out of it."""
    big = size * SUPER
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)

    pen.rounded_rectangle([0, 0, big - 1, big - 1], radius=int(big * radius_fraction), fill=BG)

    mark_px = size * mark_fraction
    inner_r = _inner_radius_for(mark_px)

    scale = (mark_px * SUPER) / (OUTER_R * 2)
    centre = big / 2

    def ellipse(cx: float, cy: float, r: float, fill):
        # The mark's own centre is (12, 12); positions are offsets from it.
        x = centre + (cx - OUTER_C[0]) * scale
        y = centre + (cy - OUTER_C[1]) * scale
        rr = r * scale
        pen.ellipse([x - rr, y - rr, x + rr, y + rr], fill=fill)

    ellipse(*OUTER_C, OUTER_R, MARK)
    ellipse(*INNER_C, inner_r, BG)

    return image.resize((size, size), Image.LANCZOS)


# The same two circles as the raster path, kept as the mark's own path so the
# scalable icon and `_icons.html` cannot drift apart.
MARK_PATH = (
    "M12 3.25A8.75 8.75 0 1 0 12 20.75A8.75 8.75 0 1 0 12 3.25Z"
    "M13.35 5.55A6.5 6.5 0 1 1 13.35 18.55A6.5 6.5 0 1 1 13.35 5.55Z"
)

SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <rect width="24" height="24" rx="5.5" fill="#161826"/>
  <g transform="translate(12 12) scale(0.82) translate(-12 -12)">
    <path fill="#b5abfc" fill-rule="evenodd" d="{MARK_PATH}"/>
  </g>
</svg>
"""


def main() -> None:
    STATIC.mkdir(parents=True, exist_ok=True)

    # The scalable one, for browsers that take it. No size floor needed: it is
    # resampled by the renderer at whatever size it is shown.
    (STATIC / "icon.svg").write_text(SVG, encoding="utf-8")

    # A tab icon, and what Google shows beside a search result. One file with
    # several sizes so each is drawn for its own resolution rather than shrunk
    # from one bitmap.
    ico_sizes = [16, 32, 48, 64]
    frames = [draw_icon(n, mark_fraction=0.70, radius_fraction=0.22) for n in ico_sizes]
    frames[-1].save(
        STATIC / "favicon.ico",
        format="ICO",
        sizes=[(n, n) for n in ico_sizes],
        append_images=frames[:-1],
    )

    # iOS home screen. No transparency and no rounding of our own: the system
    # applies its own mask, and a rounded icon inside it gets a double corner.
    draw_icon(180, mark_fraction=0.62, radius_fraction=0).save(STATIC / "apple-touch-icon.png")

    # Android, from the manifest.
    for n in (192, 512):
        draw_icon(n, mark_fraction=0.66, radius_fraction=0.22).save(STATIC / f"icon-{n}.png")

    # Maskable: Android crops to a shape of its choosing, and only the middle
    # 80% is guaranteed to survive. The tile bleeds to the edge, the mark sits
    # well inside it.
    draw_icon(512, mark_fraction=0.52, radius_fraction=0).save(STATIC / "icon-512-maskable.png")

    make_social()

    for path in sorted(STATIC.glob("*icon*")) + [STATIC / "favicon.ico"]:
        print(f"  {path.name:26} {path.stat().st_size:>7,} bytes")
    for path in sorted(BRAND.glob("*.png")):
        print(f"  brand/{path.name:20} {path.stat().st_size:>7,} bytes")


def make_social() -> None:
    """The avatar for a social profile.

    Instagram shows it as a circle, so the tile has no corners of its own: a
    rounded square inside a circular crop loses its corners anyway and leaves
    notches where the two curves disagree. Full bleed means the crop lands
    entirely on the background whatever shape it turns out to be — Instagram in
    a circle, LinkedIn in a rounded square, an open-graph card as-is.

    The mark is sized against the inscribed circle rather than the square,
    because the square's corners are exactly the part that gets thrown away.
    It fills about seven tenths of that circle: an avatar is read at 32px in a
    comment thread far more often than at 320px on a profile, and at 32px a
    polite margin is just the mark being small.

    1080 because it is the largest size worth uploading: Instagram resamples
    down to 320 on the web and 110 on a phone, and giving it more to work from
    costs nothing. The ring's light side is about 33px here, so it survives
    that journey without the size floor having to step in.
    """
    BRAND.mkdir(parents=True, exist_ok=True)
    for size in (1080, 320):
        draw_icon(size, mark_fraction=0.72, radius_fraction=0).save(
            BRAND / f"offerly-avatar-{size}.png"
        )


if __name__ == "__main__":
    main()
