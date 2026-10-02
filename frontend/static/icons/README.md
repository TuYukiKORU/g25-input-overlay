# App icon

The approved artwork is `app-icon-master.png`: a cyan T with an enlarged orange telemetry pulse on graphite. It was generated with the built-in image generation tool and approved on 2026-10-02.

`scripts/Build-AppIcon.ps1` exports the unchanged design as PNGs (32, 180, 192 and 512 px) and a Windows ICO containing 16, 24, 32, 48, 64, 128 and 256 px frames. It resizes the image without cropping or redrawing it.

The web templates share `_app_icons.html`. `scripts/Create-AppShortcut.ps1` creates the project-local Windows launcher shortcut using `app.ico`.

Final image-edit prompt:

> Edit this app icon with ONE targeted change: make the orange telemetry pulse significantly bigger, approximately 1.7 times its current width and 1.4 times its current height, with a proportionally thicker stroke. Keep it horizontally centered over the cyan T's vertical stem, at the same vertical center as the original pulse. The longer orange horizontal tails should extend noticeably to both sides of the stem. Preserve the original single peak-and-trough waveform, warm orange color and gently softened angular corners. The pulse should be prominent and readable at a small icon size while the cyan capital T remains unmistakable. Preserve EVERYTHING ELSE: the T's exact shape, size, position, cyan color, broad horizontal crossbar, centered straight stem, dark rounded-square tile, surrounding charcoal backdrop, overall framing and clean finish. Do not redesign the letter or add any new elements, text, glow or shadows. One icon only.
