# ai-marketing-digest

Applicazione Python 3.11 che raccoglie ogni giorno contenuti recenti da molte fonti AI + marketing e genera un articolo editoriale originale in inglese, con immagine AI e sito statico pubblico.

## Cosa fa

1. Legge le fonti da `sources.yaml`.
2. Scopre e valida automaticamente feed RSS/Atom dalla pagina blog. Se non trova feed validi, usa scraping HTML con `requests` e `BeautifulSoup`.
3. Rispetta `robots.txt` prima di scaricare pagine, feed e articoli.
4. Tiene solo articoli pubblicati nella finestra configurata, di default 48 ore.
5. Deduplica gli URL già processati in SQLite, ma usa comunque il corpus recente come contesto editoriale.
6. Usa gli articoli come materiale di ricerca, non come link roundup pubblico.
7. Genera un articolo quotidiano originale: tesi personale, analisi, claim discipline e takeaway pratico.
8. Tiene le fonti solo in fondo, come bibliografia compatta, cosi' il contenuto principale resta editoriale e proprietario.
9. Può inviare il risultato via email o Telegram.
10. Può generare un sito statico pubblico in `site/`, pubblicabile su GitHub Pages.
11. Usa `voice.yaml` per mantenere una prospettiva editoriale personale e non copiare il framing dei siti fonte.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Imposta almeno una chiave in `.env`:

```bash
OPENAI_API_KEY=...
# oppure
ANTHROPIC_API_KEY=...
```

Esecuzione reale:

```bash
python -m ai_marketing_digest run
```

Esecuzione senza chiamare un LLM, utile per verificare pipeline e output:

```bash
python -m ai_marketing_digest run --dry-run --no-delivery
```

Generare anche il sito locale:

```bash
python -m ai_marketing_digest run --build-site
```

Oppure rigenerare solo il sito dagli output gia' presenti:

```bash
python -m ai_marketing_digest site
```

Rigenerare includendo anche articoli gia' visti nel database:

```bash
python -m ai_marketing_digest run --include-seen
```

## Configurazione

`config.yaml` controlla finestra temporale, numero massimo di articoli, modello LLM, ranking opzionale e delivery.

`voice.yaml` controlla la voce editoriale: audience, punto di vista, regole, tono e frasi da evitare. Modificalo quando vuoi che gli articoli seguano meglio il tuo pensiero.

Variabili ambiente utili:

- `OPENAI_API_KEY` o `ANTHROPIC_API_KEY`
- `LLM_PROVIDER=auto|openai|anthropic|mock`
- `OPENAI_MODEL` e `ANTHROPIC_MODEL`
- `USE_LLM_RANKING=true` per ordinare i candidati con il modello
- `WINDOW_HOURS=48`
- `MAX_NEWSLETTER_ARTICLES=40` per decidere quanti articoli recenti usare come corpus editoriale
- `VOICE_FILE=voice.yaml`
- `IMAGE_ENABLED=true`
- `IMAGE_MODEL=gpt-image-1`
- `EMAIL_ENABLED=true`
- `TELEGRAM_ENABLED=true`

Le chiavi vanno solo in `.env` o nei secrets di GitHub Actions, mai nei file YAML versionati.

## Aggiungere fonti

Modifica `sources.yaml`:

```yaml
sources:
  - name: Nome Blog
    blog_url: https://example.com/blog/
    feed_url:
    enabled: true
```

`feed_url` può restare vuoto: l'app cerca link RSS/Atom nella pagina e prova percorsi comuni come `/feed/`, `/rss.xml`, `/feed.xml` e `/atom.xml`.

Se la pagina blog ha markup insolito, puoi aggiungere un selettore CSS per gli URL degli articoli:

```yaml
  - name: Blog con layout custom
    blog_url: https://example.com/insights/
    article_selector: ".post-card a"
    enabled: true
```

## Output

I digest vengono scritti in:

```text
output/YYYY-MM-DD.md
```

Il database SQLite di deduplica si trova in:

```text
data/digest.sqlite3
```

Il sito statico viene generato in:

```text
site/index.html
site/archive.html
site/digests/YYYY-MM-DD.html
site/feed.xml
```

Ogni file contiene:

- articolo originale quotidiano
- immagine hero generata da AI se `OPENAI_API_KEY` e `IMAGE_ENABLED=true` sono disponibili
- fonti consultate solo alla fine, come crediti/bibliografia
- breve nota di research basis senza trasformare il sito in una lista di link alle fonti

## Delivery opzionale

Email:

```bash
EMAIL_ENABLED=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_TLS=true
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM=digest@example.com
SMTP_TO=you@example.com
EMAIL_ALLOWED_TO=you@example.com
```

`EMAIL_ALLOWED_TO` e' una cintura di sicurezza: se `SMTP_TO` non combacia, l'app rifiuta l'invio. Inoltre il codice accetta un solo destinatario, senza liste, CC o BCC.

Poi avvia:

```bash
python -m ai_marketing_digest run
```

Telegram:

```bash
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## GitHub Actions

Il workflow `.github/workflows/daily.yml` gira ogni giorno alle 07:00 UTC e può essere lanciato manualmente con `workflow_dispatch`.

Il workflow `.github/workflows/publish-site.yml` genera il digest, costruisce `site/` e lo pubblica su GitHub Pages.

Configura i repository secrets:

- `OPENAI_API_KEY` o `ANTHROPIC_API_KEY`
- eventuali secrets SMTP
- eventuali secrets Telegram

Il workflow carica `output/*.md` e `data/digest.sqlite3` come artifact. Usa anche `actions/cache` per ripristinare il database SQLite tra esecuzioni successive.

Per rendere il sito visibile online con GitHub Pages:

1. Carica il progetto su un repository GitHub.
2. Vai in `Settings` -> `Pages`.
3. Come source scegli `GitHub Actions`.
4. Aggiungi `OPENAI_API_KEY` o `ANTHROPIC_API_KEY` nei repository secrets.
5. Lancia manualmente `Publish AI Marketing Digest Site` oppure aspetta il cron giornaliero.
