# Rules for this public repository

Everything committed here is public and licensed under Apache-2.0. Before you commit, check that the change
follows these rules.

1. **No identifying context.** No names of employers, clients, sectors, internal projects or project codes,
   hosts, machines, internal tools or people. Examples use invented organisations.
2. **No client material.** No client calibrations (an organisation's own scales, levels or acceptance rules),
   no client studies, documents or extracts. These load at runtime from `ATELIER_PRIVATE_DIR`, a directory
   outside the repository (see `docs/plugins.md`). `private/` and `studies/` are git-ignored as a second guard.
3. **Only content we are allowed to publish.** Method content comes from the ANSSI guide *EBIOS Risk Manager*
   v1.5 (Licence Ouverte / Open Licence, credited in `NOTICE`), or is original work. Do not copy material from
   sources without a licence that allows redistribution, even if it is freely downloadable.
4. **No secrets.** No API keys, tokens, passwords, private keys or `.env` files. GitHub secret scanning and push
   protection are on, and a push containing a recognised secret is refused; do not bypass it.
5. **The method stays as published.** The engine automates and checks the method; it does not invent new
   steps, scales or rules. Anything beyond the guide is marked as such in the docs.
6. **Deterministic levels.** Risk levels, checks and registers are computed by the engine. Generated text
   (for example a model draft) may propose content, never set a level.
7. **Commit identity.** Commit with a GitHub noreply address, never a personal or work email.
8. **Tests stay green.** `cd engine && python3 -m unittest` passes before every push.
