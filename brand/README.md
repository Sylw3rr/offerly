# Brand artwork

Artwork for places outside the product. Everything here is generated — edit the
mark, not these files:

```bash
python scripts/make_icons.py
```

| File | Where it goes |
| --- | --- |
| `offerly-avatar-1080.png` | Instagram, X, LinkedIn, Discord — the one to upload |
| `offerly-avatar-320.png` | Anywhere that rejects large uploads |

## Why the avatar is not the app icon

The app icon in `app/web/static/` is a rounded square. This one is not, and the
difference matters: Instagram crops a profile picture to a circle, and a
rounded square inside a circular crop loses its corners anyway — leaving
notches where the two curves disagree. Full bleed means the crop lands entirely
on the background, whatever shape the platform decides on.

The mark also sits larger here, filling about seven tenths of the circle. An
avatar is read at 32px beside a comment far more often than at 320px on a
profile page, and at 32px a polite margin is just the mark being small.

## Uploading

Use the 1080. Instagram resamples it down to 320 on the web and 110 on a phone,
and giving it more to work from costs nothing. Do not crop or round it first —
the platform does that, and doing it twice is what produces a ring of
background inside the circle.

Colours are the product's own: background `#161826`, mark `#b5abfc`.
