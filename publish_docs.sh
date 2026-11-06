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

# Commits de docs/ de ejecuciones anteriores cuyo push falló (p. ej. GH_PAT
# caducado). No son "desarrollo sin publicar": se suben en esta ejecución.
# Sin esto, un solo push fallido bloqueaba todas las ejecuciones siguientes
# (HEAD local ≠ main) aunque se renovara el token.
solo_docs_del_bot() {
    git merge-base --is-ancestor "$REMOTE_HEAD" HEAD &&
    [ -z "$(git log --format=%an "$REMOTE_HEAD"..HEAD | grep -vx tumtumpa-bot)" ] &&
    git diff --quiet "$REMOTE_HEAD" HEAD -- . ':(exclude)docs'
}

if [ "$REMOTE_HEAD" != "$LOCAL_HEAD" ] && solo_docs_del_bot; then
    echo "Hay commits de docs/ de ejecuciones anteriores sin subir; se suben ahora."
elif [ "$REMOTE_HEAD" != "$LOCAL_HEAD" ]; then
    echo "⚠ El HEAD local no coincide con main en GitHub — hay commits sin"
    echo "  publicar de antes (desarrollo normal del repo) que no queremos"
    echo "  subir de golpe junto con docs/. Publícalos a mano primero:"
    echo "  git push origin main   (desde $(pwd))"
    echo "  No se toca docs/ ni se publica nada en esta ejecución."
    exit 1
fi

git add docs
if git diff --cached --quiet; then
    if [ "$REMOTE_HEAD" = "$LOCAL_HEAD" ]; then
        echo "docs/ sin cambios, nada que publicar."
        exit 0
    fi
else
    git -c user.email="tumtumpa-bot@localhost" -c user.name="tumtumpa-bot" \
        commit -m "auto: actualiza docs $(date -u +%F)"
fi

if ! git push "$REMOTE_URL" HEAD:main; then
    # Deshace los commits del bot (los cambios de docs/ quedan en el árbol)
    # para que la próxima ejecución parta otra vez de main y no se atasque.
    git reset --soft "$REMOTE_HEAD"
    echo "❌ Falló el push (¿GH_PAT caducado o sin contents:write?). docs/ queda"
    echo "   pendiente; se reintentará en la próxima ejecución."
    exit 1
fi

echo "docs/ publicado en GitHub Pages."
