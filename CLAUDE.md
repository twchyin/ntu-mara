# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a single-file static HTML application — an interactive "World Map" learning journey visualizer for a 13-week database and programming course (NTU MARA). There is no build system, no package manager, and no test framework. The entire application lives in `index.html`.

## Running the Project

Open `index.html` directly in a browser — no server required. For local development with live reload, any static file server works:

```bash
python3 -m http.server 8080
# or
npx serve .
```

## Architecture

Everything is contained in `index.html` as one self-contained document:

- **Styles** — inline `<style>` block using Tailwind CSS (CDN), custom CSS for the pixel-art game aesthetic (`.map-node`, `.wave`, `.modal-overlay`, `.mc-button`), and keyframe animations (`drift`, `dashMove`, `spin`)
- **HTML structure** — a fixed `<header>` UI panel, a `#viewport` div containing the pannable/zoomable `#world-map` div, zoom controls, and a `#modal` overlay
- **JavaScript** — all logic inline in a `<script>` block at the bottom; no modules, no bundler

### Key JS concepts

**`nodes` array** — the single source of truth for all course content. Each node has `id`, `label` (e.g. "L1"), `x`/`y` pixel coordinates within the 1536×864 map canvas, `week`, `about`, `stars` (array of 3 mastery objectives), and an optional `style: "danger"` for boss nodes rendered with a skull icon.

**Pan/zoom system** — `posX`, `posY`, `scale` state variables; `updateTransform()` applies `translate(${posX}px, ${posY}px) scale(${scale})` to `#world-map`. Mouse drag, scroll wheel, and button controls all mutate these variables. `resetView()` auto-fits the 1536×864 canvas to the viewport with padding.

**`renderNodes()`** — iterates the `nodes` array and creates `.map-node` `<button>` elements positioned absolutely within `#world-map`. Nodes stagger in with a 50ms `setTimeout` delay between each.

**`drawPaths()`** — creates quadratic Bézier SVG `<path>` elements between consecutive nodes (node[i] → node[i+1]) with a random control point offset for an organic look. Rendered into the `#paths` SVG element.

**`openMap(id)`** — finds the node by ID, builds the modal HTML string, and sets `modal.style.display = 'flex'`.

### Assets

`assets/world-map.png` — the background map image (1536×864px). The `assets/islands/` directory contains SVG files for individual island regions, though these are not currently referenced in `index.html`.

## Making Changes

**Adding or editing a lesson node** — modify the `nodes` array in the `<script>` block. The `x`/`y` coordinates are pixel positions within the 1536×864 map canvas.

**Styling** — the pixel/game aesthetic relies on `VT323` (pixel font via Google Fonts) and custom CSS classes. The color palette is warm amber (`#ffdd8c`, `#c16a00`) for normal nodes and red (`#ffb39c`, `#9f1b10`) for danger/boss nodes.

**Layout** — `#world-map` is fixed at 1536×864px and CSS-transformed for pan/zoom; UI controls use `position: fixed` with `z-index: 100` to stay above the map.
