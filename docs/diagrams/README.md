# Diagrams (Graphviz DOT)

Architecture/topology diagrams in this repository use **Graphviz DOT** (not PlantUML).

## Why Graphviz

- deterministic layout with explicit constraints (`rank=same`, invisible edges, clusters)
- strict control of layering and cross-node placement
- text-only source files, diff-friendly in Git
- CI-friendly batch rendering with `dot` engine

## Directory Structure

- `docs/diagrams/src/` -> source `.dot` files
- `docs/diagrams/out/svg/` -> rendered SVG (primary output)
- `docs/diagrams/out/pdf/` -> rendered PDF (secondary output)

## Naming Conventions

- source files: `kebab-case.dot`
- output files keep the same basename:
  - `src/example.dot` -> `out/svg/example.svg`
  - `src/example.dot` -> `out/pdf/example.pdf`

## Local Rendering

Render a single diagram:

```bash
dot -Kdot -Tsvg docs/diagrams/src/<name>.dot -o docs/diagrams/out/svg/<name>.svg
dot -Kdot -Tpdf docs/diagrams/src/<name>.dot -o docs/diagrams/out/pdf/<name>.pdf
```

## Graphviz Installation

Linux (Ubuntu/Debian):

```bash
sudo apt-get update
sudo apt-get install -y graphviz
```

Windows:

```powershell
winget install --id Graphviz.Graphviz
```

## Shared Style Convention

Each DOT diagram should include:

- `rankdir=LR` for horizontal node placement at system/distributed level
- `splines=ortho`
- `compound=true`
- `newrank=true`
- explicit `rank=same` constraints where alignment must be stable
- invisible edges for layout stabilization only
- minimal technical style (neutral palette, thin borders, no decorative icons)
