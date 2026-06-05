# Monitor Biglietti TicketOne

Controlla automaticamente ogni 5 minuti la disponibilità di biglietti su TicketOne e invia una notifica Telegram quando un settore torna disponibile.

**Partita monitorata:** Ascoli vs Union Brescia — Play-off Serie C 2025/2026

---

## Come funziona

- **GitHub Actions** esegue lo script ogni 5 minuti (gratuito, nessuna VPS necessaria)
- **Playwright** (browser headless Chromium) carica la pagina TicketOne e intercetta le chiamate API interne per leggere la disponibilità dei settori
- Se un settore passa da *esaurito* a *disponibile*, ricevi una notifica **Telegram** con link diretto all'acquisto
- Lo stato viene salvato in `state.json` e committato nel repo ad ogni variazione

---

## Setup (una tantum)

### 1. Crea un Bot Telegram

1. Apri Telegram, cerca **@BotFather** e scrivi `/newbot`
2. Scegli un nome e uno username per il bot
3. Copia il **token** (formato: `123456:ABC-DEF...`)

### 2. Ottieni il tuo Chat ID

1. Avvia una conversazione con il tuo nuovo bot (cerca il suo username e premi *Start*)
2. Apri nel browser:
   ```
   https://api.telegram.org/bot<IL_TUO_TOKEN>/getUpdates
   ```
3. Cerca nel JSON il campo `"id"` dentro `"chat"` — quello è il tuo **Chat ID**

   > In alternativa manda un messaggio a **@userinfobot** su Telegram.

### 3. Aggiungi i Secret su GitHub

Nel tuo repository GitHub vai su **Settings → Secrets and variables → Actions → New repository secret** e aggiungi:

| Nome | Valore |
|------|--------|
| `TELEGRAM_BOT_TOKEN` | Il token del bot (es. `123456:ABC...`) |
| `TELEGRAM_CHAT_ID` | Il tuo chat ID (es. `987654321`) |

### 4. Abilita GitHub Actions

- Vai su **Actions** nel tuo repository e clicca **"I understand my workflows, go ahead and enable them"** se richiesto.
- Il workflow partirà automaticamente ogni 5 minuti.

---

## Test manuale

Puoi avviare il controllo manualmente da **Actions → Monitor Biglietti TicketOne → Run workflow**.

Attiva l'opzione **debug** per salvare l'HTML della pagina come artefatto e verificare cosa vede il bot.

---

## Debug locale

```bash
pip install -r requirements.txt
playwright install chromium
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy DEBUG=true python check_tickets.py
```

---

## Note

- GitHub Actions esegue i cron job **dal branch `main`** — assicurati che i file siano su `main`.
- GitHub non garantisce l'esecuzione esatta al minuto (possibile ritardo di qualche minuto sotto carico).
- Se la pagina TicketOne cambia struttura, lo script lo segnala dopo 5 controlli falliti consecutivi.
- Per fermare il monitoraggio: vai su **Actions → Monitor Biglietti TicketOne → (tre puntini) → Disable workflow**.
