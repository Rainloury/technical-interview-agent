# Security Policy

## Supported versions

Only the latest release and the `main` branch receive security fixes. Older
development snapshots and forks are not supported.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private
vulnerability reporting feature on the repository's **Security** tab. If that
feature is unavailable, contact the repository owner through a private channel
listed on their GitHub profile.

Include:

- the affected version or commit;
- a concise description of the impact;
- reproduction steps or a minimal proof of concept;
- any known mitigation;
- whether the report involves credentials, personal data, or production
  infrastructure.

Never include live credentials, personal documents, or production user data.

The maintainer will acknowledge a complete report as soon as practical, assess
the impact, and coordinate disclosure after a fix is available. Please avoid
publishing details before a coordinated disclosure date.

## Security boundaries

This service handles authentication sessions, resumes, interview content, and
private internal documents. The project treats uploaded files, retrieved
documents, tool output, and third-party API responses as untrusted data.

Report issues involving:

- authentication or session bypass;
- cross-user data access;
- prompt injection that escapes the untrusted-content boundary;
- document retrieval across owners;
- unsafe file handling;
- credential or personal-data disclosure;
- missing authorization on write or deletion endpoints;
- production configuration that disables a documented security control.

Do not test against systems or data you do not own or have permission to use.
