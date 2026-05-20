## Go runtime setup

For workflows that operate on a Go module, provision the toolchain before
the agent step begins.

### Install the toolchain

```yaml
- uses: actions/setup-go@v5
  with:
    go-version-file: go.mod
    cache: true
```

`go-version-file: go.mod` honors the module's declared Go version.

### Network egress

This workflow's lock file MUST declare:

```yaml
network:
  allowed: [defaults, go]
```

The `go` ecosystem id covers `proxy.golang.org`, `sum.golang.org`,
`storage.googleapis.com` (module mirror), and `vuln.go.dev`.

### Tool checks

```bash
command -v go >/dev/null 2>&1 || { echo "go not found" >&2; exit 1; }
go version
```

### Optional: staticcheck, govulncheck

Lint and dep-bump chores install these via `go install`:

```bash
go install honnef.co/go/tools/cmd/staticcheck@latest
go install golang.org/x/vuln/cmd/govulncheck@latest
```

Cache the Go build cache (typically `~/.cache/go-build` on Linux) and
`~/go/pkg/mod` to avoid reinstalling on every run. Use `actions/cache@v4`
with a key derived from `hashFiles('go.sum')`.
