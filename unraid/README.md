# Sublarr on Unraid

The Community Applications (CA) template for Sublarr lives in its own
dedicated templates repo (CA's preferred layout):

👉 **[github.com/Abrechen2/docker-templates](https://github.com/Abrechen2/docker-templates)**

Published template:

- [`my-sublarr.xml`](https://raw.githubusercontent.com/Abrechen2/docker-templates/main/my-sublarr.xml)

## Install

**Community Applications (preferred):** open the **Apps** tab in Unraid and
search for **Sublarr**, then click **Install**.

**Manual install (while CA approval is pending):** Unraid → **Docker** tab →
**Add Container** → paste the raw template URL above into the **Template**
field. Unraid pulls it directly.

Sublarr is self-contained — it stores everything in an embedded SQLite
database, so **no separate database container is required**. After the
container is healthy, open `http://<unraid-ip>:5765` and the first-run
onboarding wizard guides you through language, providers and automation.
Sonarr/Radarr are optional; PostgreSQL and Redis are optional advanced
backends configured via environment variables.

## Template maintenance (for the maintainer)

The canonical template URL is:

```
https://raw.githubusercontent.com/Abrechen2/docker-templates/main/my-sublarr.xml
```

### Submit to Community Apps

1. Fork [community-apps-templates](https://github.com/Squidly271/AppFeed)
   *(or follow the current CA submission instructions in the
   [Community Applications forum thread](https://forums.unraid.net/topic/57181-community-applications/))*.
2. Open a PR pointing at the `my-sublarr.xml` raw URL above.
3. Respond to reviewer feedback — common asks:
   - Pin a specific image tag instead of `latest` (override per-release if CA
     requires reproducible installs).
   - Confirm `Privileged=false` is sufficient (it is).
   - Provide a logo on a non-transparent background.
   - Provide an Unraid support-forum thread for the `<Support>` field.

### Image

The container image is published multi-arch (amd64 + arm64) to GHCR at
`ghcr.io/abrechen2/sublarr`. The template tracks `:latest`; ensure each
release is built with `docker buildx --platform linux/amd64,linux/arm64`
so `:latest` stays multi-arch.

### Icon

CA prefers a square PNG on a non-transparent background. The template's
`<Icon>` currently points at the repository `logo.png`; if a reviewer asks,
render a 512×512 PNG on a solid background and point `<Icon>` at its raw URL.
