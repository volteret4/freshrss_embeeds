#!/usr/bin/env bash
# Publica docs/ a GitHub Pages: commit + push a main si hay cambios. Requiere
# GH_PAT (token fine-grained, contents:write sobre este repo) en el .env —
# configurable desde el panel ⚙.
#
# Seguridad: antes de publicar comprueba que el HEAD local (aparte del commit
# de docs/ que vamos a crear) coincide EXACTAMENTE con el main real de GitHub.
# Si hay historial local sin subir, se aborta en vez de publicarlo de golpe.
set -euo pipefail
cd "$(dirname "$0")"

# En Docker, .git es un puntero de submodule ("gitdir: ../../.git/modules/...")
# que resuelve a una ruta del HOST inaccesible dentro del contenedor. Si el
# compose monta el gitdir real en /gitdir, usarlo explícito evita depender de
# esa resolución relativa rota.
if [ -d /gitdir ]; then
    export GIT_DIR=/gitdir
    export GIT_WORK_TREE="$(pwd)"
fi

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

if [ -z "${GH_PAT:-}" ]; then
    echo "GH_PAT no configurado (panel ⚙ o .env) — no se publica nada."
    exit 0
fi

REMOTE_URL="https://x-access-token:${GH_PAT}@github.com/volteret4/freshrss_embeeds.git"

if ! git fetch --quiet "$REMOTE_URL" main; then
    echo "❌ No se pudo contactar GitHub (revisa GH_PAT / conectividad)."
    exit 1
fi

REMOTE_HEAD="$(git rev-parse FETCH_HEAD)"
LOCAL_HEAD="$(git rev-parse HEAD)"

if [ "$REMOTE_HEAD" != "$LOCAL_HEAD" ]; then
    echo "⚠ El HEAD local no coincide con main en GitHub — hay commits sin"
    echo "  publicar de antes (desarrollo normal del repo) que no queremos"
    echo "  subir de golpe junto con docs/. Publícalos a mano primero:"
    echo "  git push origin main   (desde $(pwd))"
    echo "  No se toca docs/ ni se publica nada en esta ejecución."
    exit 1
fi

git add docs
if git diff --cached --quiet; then
    echo "docs/ sin cambios, nada que publicar."
    exit 0
fi

git -c user.email="tumtumpa-bot@localhost" -c user.name="tumtumpa-bot" \
    commit -m "auto: actualiza docs $(date -u +%F)"

git push "$REMOTE_URL" HEAD:main

echo "docs/ publicado en GitHub Pages."
