# Atelier web app

```bash
python3 app/atelier.py start   # prints http://127.0.0.1:8770/ and a one-time login link; opens nothing else
python3 app/atelier.py status
python3 app/atelier.py stop
python3 app/atelier.py token --new
```

Drafting is off until you pick a route in Settings. See `docs/app.md` (run, data, documents, drafting routes,
limits, security model, a systemd user unit template).
