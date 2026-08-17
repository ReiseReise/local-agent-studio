# Public release checklist

No item below authorizes publication. Creating a public repository, pushing source, and publishing a release require an explicit confirmation immediately beforehand.

- [ ] Windows clean installation from the exact candidate source passes.
- [ ] `ruff`, `pytest`, public-repository scan, and wheel build pass on Windows.
- [ ] Browser journeys pass at desktop and narrow viewport.
- [ ] No private names, usernames, chat samples, absolute paths, tokens, or historical UIA code exist.
- [ ] Dependency vulnerability and license reviews are recorded.
- [ ] `scripts/generate_sbom.py` produces the candidate SBOM.
- [ ] Source archive checksum is recorded.
- [ ] Chinese README and English quick start match the tested commands.
- [ ] `v0.1.0` notes state the Windows, local-only, no-connector and no-live-WeChat boundaries.
- [ ] Reise confirms public creation and release for the final candidate commit.
