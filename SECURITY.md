# Security policy

## Reporting a vulnerability

Please report security issues privately via GitHub's **"Report a
vulnerability"** button (repository → Security → Advisories), or by opening a
minimal issue asking for a private contact channel — do **not** disclose
details in a public issue.

## Security posture

Hose Assistant is a Home Assistant add-on with a deliberately small attack
surface:

- **No exposed ports.** The web UI is served only through Home Assistant
  Ingress, behind Home Assistant's own authentication.
- **Minimal outbound data.** Only your latitude/longitude are sent to
  Open-Meteo (weather, no account). AI features — only when you explicitly
  invoke them — send your irrigation configuration to the provider you
  configured. Nothing else leaves your instance.
- **Secrets** (AI API keys) live in the Supervisor-managed add-on options,
  not in the add-on's database or its backup export (`/data`).
- **Valve safety is defence-in-depth**, not just software: every valve open
  schedules a persisted watchdog turn-off, all valves close on start/error,
  and there is a hard per-zone max-runtime cap.

## Dependencies

Automated dependency and security updates are handled by Dependabot
(`.github/dependabot.yml`): weekly checks for the backend (pip), frontend
(npm) and CI actions, plus GitHub security alerts. Backend dependencies use
`>=` ranges, so each add-on rebuild also picks up the latest compatible
patch releases.
