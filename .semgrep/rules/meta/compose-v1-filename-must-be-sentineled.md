<!--
Test cases for meta-compose-v1-filename-must-be-sentineled (run via `just semgrep-test`).
Each target line is preceded by a semgrep annotation comment on the line ABOVE it:
ruleid marks an expected match, ok marks an expected non-match. The annotation syntax
is intentionally not spelled out here so this header is not parsed as a test annotation.
-->

<!-- ok: meta-compose-v1-filename-must-be-sentineled -->
<prohibited-filename>docker-compose.yaml</prohibited-filename>

<!-- ok: meta-compose-v1-filename-must-be-sentineled -->
<prohibited-filename>docker-compose.yml</prohibited-filename>

<!-- ok: meta-compose-v1-filename-must-be-sentineled -->
<prohibited-filename>  docker-compose.yaml  </prohibited-filename>

<!-- ruleid: meta-compose-v1-filename-must-be-sentineled -->
Never use docker-compose.yaml for new projects.

<!-- ruleid: meta-compose-v1-filename-must-be-sentineled -->
The legacy docker-compose.yml file is deprecated.

<!-- ruleid: meta-compose-v1-filename-must-be-sentineled -->
File paths like /path/to/docker-compose.yaml must be avoided.

<!-- ruleid: meta-compose-v1-filename-must-be-sentineled -->
Inline code `docker-compose.yaml` without the sentinel tag is still a violation.

<!-- ruleid: meta-compose-v1-filename-must-be-sentineled -->
Mixed content: use compose.yaml (NOT docker-compose.yaml) is a violation.
