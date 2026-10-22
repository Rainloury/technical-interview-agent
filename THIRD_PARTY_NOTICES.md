# Third-Party Notices

Technical Interview Agent is distributed under the Apache License 2.0. Its
dependencies and bundled assets remain under their respective licenses.

The authoritative dependency versions are recorded in `uv.lock` and
`web/package-lock.json`. When redistributing this project, retain the license
files and copyright notices shipped with dependencies.

## Bundled fonts

The web client includes the following font software:

| Asset | Copyright | License |
| --- | --- | --- |
| Space Grotesk variable font | Copyright 2020 The Space Grotesk Project Authors | SIL Open Font License 1.1 |
| JetBrains Mono variable font | Copyright 2020 The JetBrains Mono Project Authors | SIL Open Font License 1.1 |

The complete OFL 1.1 text is bundled at:

- `web/public/fonts/SpaceGrotesk-OFL.txt`
- `web/public/fonts/JetBrainsMono-OFL.txt`

## Runtime and build dependencies

The Python and JavaScript dependency trees include packages under permissive
licenses such as Apache-2.0, MIT, BSD, ISC, MPL-2.0, Python Software Foundation
License, and CC0. Before publishing a binary distribution, generate an
SBOM/license inventory for the exact locked dependency set and review any
license changes introduced by dependency updates.

## Services and trademarks

The project can connect to independently deployed services such as model
providers, Ollama, PostgreSQL, Redis, S3-compatible storage, and email
providers. Those services and their models are not included in this
repository and remain subject to their own terms and licenses.

Product and company names mentioned in documentation are trademarks of their
respective owners. Their use does not imply endorsement.
