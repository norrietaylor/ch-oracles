## Go build commands

Default verification commands for Go modules. Workers and lint chores
invoke these unless `AGENTS.md` overrides them.

### Verification gate

Every command exits 0 before a PR opens:

```bash
go build ./...
test -z "$(gofmt -l .)"
go vet ./...
staticcheck ./...
go test ./...
```

`test -z "$(gofmt -l .)"` exits non-zero if any file needs formatting; the
empty-output check is the canonical Go formatting gate.

### Lint commands

`mode: report`:

```bash
gofmt -l .             # lists files needing format
go vet ./...
staticcheck ./...
```

`mode: autofix`:

```bash
gofmt -w .
goimports -w .         # if goimports is installed
# go vet and staticcheck have no --fix mode; findings stay reported.
```

### Dep-bump commands

```bash
go get -u=patch ./...
go mod tidy
govulncheck ./...      # reject if any vulnerability surfaces after upgrade
```

A patch-level bump is rejected if:

- `go.mod` major or minor version changed (only patch transitions are
  allowed for any direct or indirect dependency).
- `govulncheck` reports any vulnerability with severity `high` or `critical`
  after the upgrade.
- The Go toolchain directive in `go.mod` changed.
