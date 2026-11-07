# Runs the local agent so the frontend in ./frontend can reach it.
#
# Why this exists:
# Since LiveKit CLI v2.19.0, `lk agent dev` registers the agent under a random
# `dev-<id>` deployment so it never receives production traffic. The frontend
# targets production (it dispatches by agent name only, with no deployment), so
# a plain `lk agent dev` never joins the room and the browser waits forever.
#
# Forcing the production deployment makes the standard frontend work:
#   LIVEKIT_AGENT_DEPLOYMENT=production  ->  registered worker {"deployment": ""}
#
# Usage:
#   .\scripts\run-agent.ps1
#
# Remove this behaviour by unsetting the variable below (or run
# `lk agent dev --deployment production` directly for the same effect).

$env:LIVEKIT_AGENT_DEPLOYMENT = "production"
lk agent dev @args
