#!/bin/zsh
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Ambiente .venv non trovato. Avvia prima start.command."
  read "unused?Premi Invio per chiudere..."
  exit 1
fi

source .venv/bin/activate

echo "Invio newsletter email..."
python -m ai_marketing_digest run --include-seen --build-site

echo ""
echo "Fatto. Se SMTP e App Password sono corretti, l'email e' stata inviata."
read "unused?Premi Invio per chiudere..."
