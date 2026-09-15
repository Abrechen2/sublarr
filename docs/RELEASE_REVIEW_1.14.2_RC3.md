# 1.14.2-rc.3 review - 2026-09-15

Base: `800e7b82` (`1.14.2-rc.2`). This iteration changes Docker packaging and
release documentation; application behavior is unchanged.

## Finding

The local RC.2 image contains `/app/instance/dev_local.db` (929,792 bytes).
Read-only inspection confirmed two plaintext development credentials in its
`config_entries` table: `api_key` and `ui_session_secret`. No values were logged.
The developer database files are untracked, so local build context filtering
is necessary even when Git is clean. The deployment report also confirms the
same file in the published stable image; that separate registry inspection
was not repeated during this preparation.

The configured database default is `/config/sublarr.db`. No production code
references `dev_local.db`. The current local development configuration points
to a different database; both of its credentials differ from the exposed
values, including comparison after in-memory decryption of the API key.
No development listener was found on the usual two local ports. These checks
do not prove that no older or remote development instance still uses the
exposed credentials. Its identity and credential rotation remain unresolved.

## Fix

- Recursive Docker exclusions cover `*.db*`, `*.sqlite*` (including sidecars
  and backup extensions), encryption keys, local instance/dev state,
  tests, coverage reports, logs, virtual environments and Python caches.
- A native-platform `backend-source` build stage checks the filtered sources
  independently of `.dockerignore`. It fails on forbidden paths and on the
  SQLite header, including a renamed database without a database extension.
- The runtime stage copies only the audited source stage. Rejected data is
  never copied into an earlier layer of the resulting runtime image.
- The existing 1.14.2 changelog and DE/EN release notes describe the incident.
  Earlier image versions still retain their original contents; a new image
  does not revoke credentials distributed in an old one.

## SubSource acceptance remains open

The RC.2 deployment report shows `subscene`, not `subsource`, in the enabled
provider lists on both RC and production. These are separate providers. RC.3
updates the setup instructions to require both explicit SubSource activation
and a valid API key. A successful keyed live search and download are still
required to accept #207. Provider lists and credentials were not changed by
this packaging fix.

## Validation

- Real Docker build-context probes: recursive exclusions pass with synthetic
  database/sidecar/env/key/test/coverage fixtures at multiple depths, while
  keeping application, database and cache module files. Restoring the RC.2 ignore
  rules causes the source audit to reject the build. A renamed SQLite fixture
  is also rejected with the corrected ignore rules.
- Backend Ruff lint and formatting pass (1,254 existing backend files), and
  the new build audit passes Ruff separately. Application code is unchanged;
  the RC.2 full-run results remain applicable. An additional 82 configuration,
  server, AnimeTosho, SubSource and sweep regression tests pass for RC.3.
- Frontend ESLint, TypeScript and all 1,313 tests in 142 files pass.
- A local multi-architecture image built successfully for `linux/amd64` and
  `linux/arm64`. Both start with fresh temporary data and return HTTP 200,
  `status=healthy`, `version=1.14.2-rc.3`. Running architectures are `x86_64`
  and `aarch64`; the running arguments match the image command on both.
- An OCI archive inspection traversed both platform manifests and all 24
  unique runtime image layers, checking 2,484 files under `/app` and `/config`.
  No forbidden paths or SQLite headers were found, including in earlier layers.
- `/app/instance`, `/app/tests`, `/app/htmlcov`, `/app/dev`, `coverage.json` and
  `coverage.xml` are absent from the corrected image. Those paths account for
  93,364,227 bytes (about 89 MiB) of file contents in the local RC.2 image.
- GitNexus change analysis reports low risk and no affected application
  execution flows, including an independent fresh-index check. The main index
  also refreshed successfully with its embeddings preserved after initial
  WAL warnings. All temporary smoke containers were removed.

Verified local image: `sublarr:1.14.2-rc.3-review` (also tagged `-verified`).
OCI index digest:
`sha256:2b30e6966c3ebcebc3dde574ba38cefccad3a389fb682580f32a9b874443f730`.

## Release status

Prepared for `1.14.2-rc.3`. Registry publication and deployment are separate
from this local preparation. Stable promotion is blocked until the corrected
image has been verified and accepted. Credential rotation remains a separate
incident follow-up after identifying any instance still using the old values.

## Reference

[Docker build-context documentation](https://docs.docker.com/build/concepts/context/#dockerignore-files)
defines `**` as matching directories at any depth, including zero directories.
