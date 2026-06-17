#!/bin/zsh
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Ambiente .venv non trovato. Avvia prima start.command."
  read "unused?Premi Invio per chiudere..."
  exit 1
fi

source .venv/bin/activate

echo "Genero il sito statico da output/*.md..."
python -m ai_marketing_digest site

echo ""
echo "Apro il sito locale."
open site/index.html

echo ""
read "unused?Premi Invio per chiudere..."
