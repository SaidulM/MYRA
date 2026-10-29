# MYRA skills

Production built-in skills currently live in `backend/skill_registry.py` so
their schemas, permissions, timeouts and handlers are reviewed with the
core code.

This folder is reserved for a future signed/reviewed external-skill format.
MYRA does not currently execute arbitrary files placed here; that prevents
an untrusted download from silently becoming computer-control code.
