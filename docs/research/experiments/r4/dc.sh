#!/bin/bash
# compose wrapper for round-4 experiments (project g3x, test-only override)
cd /home/user/BI-Wizard
exec docker compose -p g3x --env-file /home/user/BI-Wizard/_workspace/qa/g3x.env -f compose.yml -f _workspace/qa/x25-override.yml "$@"
