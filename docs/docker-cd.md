# Docker CD

The repository includes a GitHub Actions continuous delivery workflow in [.github/workflows/docker-cd.yml](../.github/workflows/docker-cd.yml).

## What it does

On pushes to `main`, the workflow:

- builds the node image from `docker/Dockerfile.base`;
- pushes the image to GitHub Container Registry;
- updates the rolling tags for the latest build.

When you push a version tag such as `v1.0.0`, the workflow:

- builds and publishes the image for that tagged commit;
- creates the corresponding GitHub Release;
- attaches a small text asset with pull and run commands.

Pull requests targeting `main` still validate that the Docker image builds, but they do not publish packages or releases.

## Published image

The workflow publishes the image to:

```text
ghcr.io/<owner>/<repo>
```

For pushes on `main`, the workflow publishes:

- `:latest`
- `:main`
- `:sha-<full-commit-sha>`

For version tags such as `v1.0.0`, the workflow also publishes:

- `:v1.0.0`
- `:sha-<full-commit-sha>`

For reproducible deployments, prefer the immutable digest shown in the release page.

## How to use a release

Create and push a version tag on the commit you want to release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

1. Open the repository Releases page.
2. Pick the release matching the version tag, for example `v1.0.0`.
3. Copy the digest-based `docker pull` command from the release body or the attached `docker-node-release.txt`.

Example:

```bash
docker pull ghcr.io/<owner>/<repo>@sha256:<digest>
docker run --rm -p 9000:9000 -p 10000:10000 \
  -e NODE_ID=node-1 \
  -e HOST=0.0.0.0 \
  -e PORT=9000 \
  -e WEB_API_PORT=10000 \
  -e BOOTSTRAP_PEERS= \
  ghcr.io/<owner>/<repo>@sha256:<digest>
```

After startup, the node exposes:

- TCP traffic on port `9000`
- HTTP API on port `10000`

You can then query endpoints such as:

- `http://localhost:10000/api/state`
- `http://localhost:10000/api/membership`
- `http://localhost:10000/api/introspection`

## Repository settings required

The workflow uses the built-in `GITHUB_TOKEN`, so no extra registry secret is needed.

Make sure:

- Actions are enabled for the repository;
- workflow permissions allow `Read and write permissions`;
- package permissions are not restricted in a way that blocks pushes to GHCR.
