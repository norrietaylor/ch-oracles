# Go

## Wrappers installed for a Go consumer

- `chore-style-go.yml` — `gofmt` + `goimports` + `go vet` + `staticcheck`;
  mode: report | autofix.
- `trivial-dep-bump-go.yml` — patch-level module updates with auto-merge.
- Universal wrappers.

## Toolchain provisioning

```yaml
- uses: actions/setup-go@v5
  with:
    go-version-file: go.mod
    cache: true
```

The Go version is read from `go.mod`.

## Verification commands

Defaults (from `shared/go-build-commands.md`):

```bash
go build ./...
test -z "$(gofmt -l .)"
go vet ./...
staticcheck ./...
go test ./...
```

Override via `## Build Commands (ch-oracles override)` in
`.github/AGENTS.md`.

## Network egress

The Go chore's lock file declares `network.allowed: [defaults, go]`,
unioning in `proxy.golang.org`, `sum.golang.org`, and `vuln.go.dev`.

## Limitations

- Patch-level bump rejects any change to `go.mod`'s `go` or `toolchain`
  directive.
- `govulncheck ./...` runs as the security gate; the chore rejects on any
  high/critical finding post-upgrade.
- staticcheck findings in `mode: autofix` block the PR (staticcheck has
  no `--fix`).
