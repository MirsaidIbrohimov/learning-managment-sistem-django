#!/usr/bin/env bash
# Serverda yangi kodni işga tuşiriş: ./deploy.sh
#
# Tartib: baza zaxirasi -> git pull -> kutubxonalar -> migrate -> collectstatic -> restart.
# collectstatic şart: CSS/JS ni nginx (Engintron) staticfiles/ dan beradi, usiz eski fayl qoladi.
# restart şart: Passenger qayta işga tuşmaguncha Python kodi va shablonlar eskiçasiga qoladi.
# Biror qadam xato bersa skript töxtaydi — keyingi qadamlar bajarilmaydi.
set -euo pipefail

cd "$(dirname "$0")"

VENV="${VENV:-/home/itcacade/virtualenv/lmsv1/3.10/bin/activate}"
if [ -f "$VENV" ]; then
    # shellcheck disable=SC1090
    source "$VENV"
else
    echo "Diqqat: virtualenv topilmadi ($VENV), joriy python işlatiladi."
fi

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }

step "1/6 Baza zaxirasi"
if [ -f db.sqlite3 ]; then
    mkdir -p private_backups
    backup="private_backups/db-$(date +%Y%m%d-%H%M%S).sqlite3"
    # sqlite3 .backup işlayotgan bazadan ham butun nusxa oladi; yöq bölsa oddiy nusxa
    if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 db.sqlite3 ".backup '$backup'"
    else
        cp -p db.sqlite3 "$backup"
    fi
    echo "Saqlandi: $backup"
    # Faqat oxirgi 10 ta zaxira qoladi
    ls -1t private_backups/db-*.sqlite3 2>/dev/null | tail -n +11 | xargs -r rm -f
else
    echo "db.sqlite3 yöq — ötkazib yuborildi."
fi

step "2/6 Kodni yangilaş (git pull)"
before=$(git rev-parse HEAD)
if ! git pull --ff-only; then
    echo
    echo "git pull bajarilmadi. Serverda qölda özgartirilgan fayllar bölişi mumkin:"
    git status --short
    echo "Heç narsa özgartirilmadi. Yuqoridagi fayllarni tekşirib, qayta işga tuşiring."
    exit 1
fi
after=$(git rev-parse HEAD)

step "3/6 Kutubxonalar"
if [ "$before" != "$after" ] && git diff --name-only "$before" "$after" | grep -qx 'requirements.txt'; then
    pip install -r requirements.txt
else
    echo "requirements.txt özgarmagan — ötkazib yuborildi."
fi

step "4/6 Migratsiyalar"
python manage.py migrate --noinput

step "5/6 Statik fayllar (collectstatic)"
python manage.py collectstatic --noinput

step "6/6 Saytni qayta işga tuşiriş"
mkdir -p tmp
touch tmp/restart.txt

echo
git log -1 --format='Tayyor. Joriy versiya: %h — %s (%ci)'
echo "Brauzerda Ctrl + F5 bilan yangilang."
