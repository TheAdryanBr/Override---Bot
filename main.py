# debug_env.py - Substitua temporariamente seu main.py por esse arquivo,
# faça deploy no Render, cole aqui a saída dos logs.

import os
import sys
import time

print("=== DEBUG ENV START ===", flush=True)
print("PID:", os.getpid(), "USER:", os.environ.get("USER"), flush=True)

keys = sorted(list(os.environ.keys()))
print("TOTAL ENV VARS:", len(keys), flush=True)

for k in keys:
    if k == "DISCORD_TOKEN":
        v = os.environ.get(k)
        if v:
            print(f"{k} = [PRESENT] len={len(v)} first4={v[:4]} last4={v[-4:]}", flush=True)
        else:
            print(f"{k} = [MISSING OR EMPTY]", flush=True)
    else:
        # só mostramos as chaves para evitar vazar segredos
        print(k, flush=True)

# Extra: print a couple of env vars you'll likely set
print("---- quick-check specific vars ----", flush=True)
for check in ("DISCORD_TOKEN", "GUILD_ID", "BOOSTER_ROLE_ID", "CUSTOM_BOOSTER_ROLE_ID"):
    val = os.environ.get(check)
    if val is None:
        print(f"{check}: NOT SET", flush=True)
    else:
        if check == "DISCORD_TOKEN":
            print(f"{check}: present, len={len(val)}", flush=True)
        else:
            print(f"{check}: {val}", flush=True)

print("=== DEBUG ENV END ===", flush=True)

# para evitar que o processo continue em loop no Render, encerraremos com sucesso
sys.exit(0)
