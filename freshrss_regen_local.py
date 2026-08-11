#!/usr/bin/env python3
"""Regenera docs/*.html + index.html usando SOLO lo que ya hay en disco --
sin tocar la red ni FreshRSS. Aplica el filtro de "escuchados" (freshrss_db)
sobre los embeds ya publicados en cada feed (vía _load_existing_embeds,
la misma función que usa freshrss_html_generator.py en cada corrida
normal para no perder el histórico).

Pensado para ejecutarse tras cada /api/listened: antes, marcar un solo
ítem como escuchado disparaba un refetch completo de todos los feeds
contra la API de FreshRSS (varios minutos); esto tarda segundos porque
no hace ninguna petición de red.

Uso:
    python freshrss_regen_local.py --output-dir docs
"""

import argparse
import os

from freshrss_html_generator import generate_feed_html
from freshrss_html_index import scan_embeds_directory, generate_index_html

EMPTY_EMBEDS = {"bandcamp": [], "youtube": [], "soundcloud": []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="docs")
    parser.add_argument("--items-per-page", type=int, default=8)
    parser.add_argument("--max-pages-buttons", type=int, default=15)
    args = parser.parse_args()

    if not os.path.isdir(args.output_dir):
        print(f"✗ No existe {args.output_dir}")
        return

    html_files = [
        f for f in os.listdir(args.output_dir)
        if f.endswith(".html") and f != "index.html"
    ]

    print(f"🔄 Regenerando {len(html_files)} feed(s) en local (sin red)...")
    for html_file in sorted(html_files):
        # Mismo criterio que scan_embeds_directory() en freshrss_html_index.py
        # para reconstruir un nombre de feed a partir del nombre de archivo --
        # sanitize_feed_name() es idempotente sobre un nombre ya saneado, así
        # que el archivo de salida resultante es el mismo de siempre.
        feed_name = html_file[:-5].replace("_", " ")
        generate_feed_html(
            feed_name, EMPTY_EMBEDS, args.output_dir,
            args.items_per_page, args.max_pages_buttons,
        )
        print(f"  ✓ {feed_name}")

    feeds = scan_embeds_directory(args.output_dir)
    generate_index_html(feeds, args.output_dir)
    print("✅ index.html regenerado")


if __name__ == "__main__":
    main()
