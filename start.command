#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo ""
echo "== ai-marketing-digest =="
echo "Creo/uso l'ambiente Python, installo le dipendenze e genero un digest di prova."
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "Errore: python3 non trovato."
  echo "Installa Python da https://www.python.org/downloads/ oppure con Homebrew."
  echo ""
  read "unused?Premi Invio per chiudere..."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Creo ambiente virtuale .venv..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "Aggiorno pip..."
python -m pip install --upgrade pip

echo "Installo dipendenze..."
python -m pip install -r requirements.txt

if [ ! -f ".env" ]; then
  echo "Creo .env da .env.example..."
  cp .env.example .env
fi

echo ""
echo "Genero digest di prova senza usare API LLM..."
rm -f data/demo_digest.sqlite3
DB_PATH=data/demo_digest.sqlite3 OUTPUT_DIR=output/demo python -m ai_marketing_digest run --dry-run --no-delivery

echo ""
echo "Fatto. Apro la cartella output."
open output/demo

echo ""
echo "Se vuoi usare la generazione AI vera, apri il file .env e inserisci OPENAI_API_KEY o ANTHROPIC_API_KEY."
echo ""
read "unused?Premi Invio per chiudere..."
