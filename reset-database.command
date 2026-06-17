#!/bin/zsh

cd "$(dirname "$0")"

echo ""
echo "Questo cancella il database di deduplica reale:"
echo "data/digest.sqlite3"
echo ""
echo "Usalo solo se vuoi rigenerare da zero gli articoli gia' visti."
echo ""
read "answer?Scrivi RESET e premi Invio per continuare: "

if [ "$answer" != "RESET" ]; then
  echo "Operazione annullata."
  read "unused?Premi Invio per chiudere..."
  exit 0
fi

rm -f data/digest.sqlite3
echo "Database cancellato. Alla prossima esecuzione l'app ripartira' da zero."
read "unused?Premi Invio per chiudere..."
