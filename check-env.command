#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo ""
echo "File .env usato dall'app:"
echo "$(pwd)/.env"
echo ""

if [ ! -f ".env" ]; then
  echo "ERRORE: .env non trovato in questa cartella."
  read "unused?Premi Invio per chiudere..."
  exit 1
fi

echo "Impostazioni email lette da .env:"
echo ""

python_code='
from pathlib import Path
from dotenv import dotenv_values

env_path = Path(".env")
values = dotenv_values(env_path)
keys = [
    "EMAIL_ENABLED",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_TLS",
    "SMTP_USERNAME",
    "SMTP_FROM",
    "SMTP_TO",
    "EMAIL_ALLOWED_TO",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
]

for key in keys:
    value = values.get(key)
    if value is None or value == "":
        shown = "(vuoto)"
    elif "KEY" in key or "PASSWORD" in key:
        shown = "(presente, nascosto)"
    else:
        shown = value.strip()
    print(f"{key}={shown}")

password = values.get("SMTP_PASSWORD")
print(f"SMTP_PASSWORD={'\''(presente, nascosta)'\'' if password else '\''(vuoto)'\''}")
'

if [ -x ".venv/bin/python" ]; then
  .venv/bin/python -c "$python_code"
else
  python3 -c "$python_code"
fi

echo ""
read "unused?Premi Invio per chiudere..."
