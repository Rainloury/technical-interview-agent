# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Apache-2.0 licensing and open-source project governance files.
- Locally served Space Grotesk and JetBrains Mono font assets with their OFL
  notices.
- Release checks for public repository metadata, internal-host leaks, and font
  assets.

### Changed

- Public configuration examples now use placeholder or local service addresses.
- The README is organized around public onboarding, architecture, development,
  deployment, and support.

### Security

- This file records the public-release preparation performed before the
  repository is made public.

## [0.1.0] - 2026-10-22

### Added

- Technical interview agent API and CLI with bounded planning, tool use, tracing,
  and evaluation support.
- Account, session, CSRF, resume, interview, report, review, and data-deletion
  workflows.
- Private internal-document RAG using pgvector, lexical BM25-style retrieval,
  reciprocal rank fusion, and lexical degradation.
- Batch document upload, per-file indexing, owner isolation, and automatic
  retrieval during question answering.
- React web client, PostgreSQL migrations, asynchronous worker, local and
  production Compose definitions, and quality automation.
