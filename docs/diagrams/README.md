# Diagrams

Architecture and interaction diagrams use **Graphviz DOT** and **PlantUML**.

## Formats

- Graphviz DOT (`.dot`) is used where deterministic layout and explicit graph constraints matter.
- PlantUML (`.puml`) is used for sequence, activity, deployment, and domain-model diagrams.
- Both formats are text-based and diff-friendly.

## Directory Structure

- `docs/diagrams/src/` -> source `.dot` and `.puml` files
- `docs/diagrams/out/svg/` -> rendered SVG (primary output)
- `docs/diagrams/out/pdf/` -> rendered PDF (secondary output)
- `docs/diagrams/tools/plantuml.jar` -> pinned PlantUML `v1.2026.3` renderer

## Naming Conventions

- source files: `kebab-case.dot` or `kebab-case.puml`
- output files keep the same basename:
  - `src/example.dot` -> `out/svg/example.svg`
  - `src/example.dot` -> `out/pdf/example.pdf`

## Local Rendering

Render a single diagram:

```bash
dot -Kdot -Tsvg docs/diagrams/src/<name>.dot -o docs/diagrams/out/svg/<name>.svg
dot -Kdot -Tpdf docs/diagrams/src/<name>.dot -o docs/diagrams/out/pdf/<name>.pdf
java -jar docs/diagrams/tools/plantuml.jar -tsvg -o ../out/svg docs/diagrams/src/<name>.puml
java -jar docs/diagrams/tools/plantuml.jar -tpdf -o ../out/pdf docs/diagrams/src/<name>.puml
```

## Renderer Installation

Linux (Ubuntu/Debian):

```bash
sudo apt-get update
sudo apt-get install -y graphviz default-jre
```

Windows:

```powershell
winget install --id Graphviz.Graphviz
winget install --id EclipseAdoptium.Temurin.21.JRE
```

## Graphviz Style Convention

Each DOT diagram should include:

- `rankdir=LR` for horizontal node placement at system/distributed level
- `splines=ortho`
- `compound=true`
- `newrank=true`
- explicit `rank=same` constraints where alignment must be stable
- invisible edges for layout stabilization only
- minimal technical style (neutral palette, thin borders, no decorative icons)
