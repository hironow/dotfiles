# Test cases for meta-compose-v1-filename-must-be-sentineled
#
# Run: semgrep --test --config ../../../rules/meta/
#
# Convention:
#   <!-- ruleid: <rule-id> --> on the line ABOVE an expected match
#   <!-- ok:     <rule-id> --> on the line ABOVE an expected non-match

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
