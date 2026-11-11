"""Auditor dei calcoli (TASK-73…82).

Verifica i numeri che vedono gli utenti leggendo l'output dei tool MCP. Contratto in
``docs/auditor/architecture.md``. Moduli: ``registry`` (regole), ``context`` (contesto
memoizzato), ``runner`` (esecuzione), ``report`` (report JSON/Markdown), ``__main__`` (CLI),
``rules/`` (regole dei gruppi A-D).

Nessuna re-export e nessun import pesante qui: importare una regola non deve caricare il motore.
"""
