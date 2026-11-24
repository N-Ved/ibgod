# Contributing

Thanks for helping improve IB God. Please keep changes focused, explain user-visible behavior, and avoid
including study materials, databases, screenshots containing personal information, credentials, or deployment
secrets in commits.

## Development setup

The supported runtime is Python 3.13 in the provided container. For an isolated integration environment:

```bash
cp .env.example .env
mkdir -p library filebrowser-data data
deploy/dev-up.sh
```

The development helper starts a container on `127.0.0.1:18081` with a fake user. Stop it with
`deploy/dev-up.sh down`.

## Checks

Before opening a pull request, run:

```bash
python3 -m compileall -q app tests
git diff --check
```

If your change affects API or planning behavior, also run the relevant scripts in `tests/` while the
development container is running. Describe any environment-dependent checks that could not be run.

## Pull requests

Pull requests should include a concise problem statement, the approach taken, validation performed, and any
configuration or migration notes. Keep unrelated refactors out of feature or bug-fix changes.
