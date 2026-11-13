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

- Split the React client into per-route lazy chunks so the initial bundle no
  longer contains every page.
- Resolve E2E temporary files from the operating system temp directory with a
  shared `E2E_TEMP_DIR` override instead of hard-coded `/private/tmp` paths.
- Move Vitest settings into `vitest.config.ts` and type-check production builds
  with a dedicated `tsconfig.build.json`, so container builds no longer depend
  on files excluded by `.dockerignore`.
- Reorganize `web/src` into `app/`, `features/<domain>/` and `shared/` layers
  behind an `@/` path alias, with ESLint rules that forbid reverse imports
  (see ADR-0013); historical docs keep their original paths and rely on the
  ADR mapping table.
- Split the 4,571-line stylesheet by its existing sections, and split the API
  client into HTTP, SSE and per-domain endpoint modules behind the unchanged
  `api` facade. Type definitions are now grouped per domain.
- Consolidate four validation modules into one and extract shared upload rules;
  extract domain view components for QA answers and document rows.
- Public configuration examples now use placeholder or local service addresses.
- The README is organized around public onboarding, architecture, development,
  deployment, and support.

### Fixed

- Bound ordinary API requests with a 15-second timeout and a retryable
  `request_timeout` error; SSE streams remain unaffected.
- Handle 401 responses globally for both queries and mutations while signed in,
  instead of only on page-level query errors.
- Restore security response headers on Nginx locations that declare their own
  `add_header` directives.
- Remove the remaining react-refresh lint warnings and the unhandled MSW
  requests and `act()` warnings from the frontend test suite.

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
