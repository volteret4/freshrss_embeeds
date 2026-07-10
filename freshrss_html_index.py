#!/usr/bin/env python3
"""
Script para generar un index.html con todos los feeds de FreshRSS embeds.
Lee el directorio freshrss_embeds y crea un índice navegable.

MEJORAS:
- Tema oscuro con color de fondo #1f1f28
- Diseño actualizado con la paleta de colores oscura
"""

import os
import re
import json
import argparse
from pathlib import Path
from html import escape
from datetime import datetime


def scan_embeds_directory(directory):
    """
    Escanea el directorio buscando archivos HTML y extrae datos de los embeds incrustados.

    Returns:
        Lista de diccionarios con información de cada feed
    """
    feeds = []

    if not os.path.exists(directory):
        print(f"✗ El directorio {directory} no existe")
        return feeds

    # Buscar archivos HTML
    html_files = [f for f in os.listdir(directory) if f.endswith('.html') and f != 'index.html']

    print(f"🔍 Escaneando {directory}...")
    print(f"📄 Archivos HTML encontrados: {len(html_files)}\n")

    for html_file in sorted(html_files):
        # Obtener el nombre base del archivo
        base_name = html_file[:-5]  # Quitar .html

        feed_info = {
            'html_file': html_file,
            'name': base_name.replace('_', ' '),
            'total_embeds': 0,
            'bandcamp': 0,
            'youtube': 0,
            'soundcloud': 0,
            'pages': 0,
            'latest_date': None
        }

        # Leer el HTML y extraer datos del JavaScript
        html_path = os.path.join(directory, html_file)
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()

            # Buscar allPagesData en el JavaScript
            pages_data_match = re.search(
                r'const allPagesData = ({.+?});',
                html_content,
                re.DOTALL
            )

            if pages_data_match:
                pages_data_json = pages_data_match.group(1)
                data = json.loads(pages_data_json)
                feed_info['pages'] = len(data)

                # Contar embeds por tipo
                latest_timestamp = 0
                for page_num, page_data in data.items():
                    for item in page_data:
                        feed_info['total_embeds'] += 1

                        if item['type'] == 'bandcamp':
                            feed_info['bandcamp'] += 1
                        elif item['type'] == 'youtube':
                            feed_info['youtube'] += 1
                        elif item['type'] == 'soundcloud':
                            feed_info['soundcloud'] += 1

                        # Encontrar fecha más reciente
                        try:
                            date_str = item['date']
                            date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
                            timestamp = date_obj.timestamp()
                            if timestamp > latest_timestamp:
                                latest_timestamp = timestamp
                                feed_info['latest_date'] = date_str
                        except:
                            pass

                print(f"  ✓ {feed_info['name']}: {feed_info['total_embeds']} embeds ({feed_info['pages']} páginas)")
            else:
                print(f"  ⚠  {html_file} (no se encontró allPagesData)")
        except Exception as e:
            print(f"  ⚠  Error leyendo {html_file}: {e}")

        feeds.append(feed_info)

    return feeds


def generate_index_html(feeds, output_dir):
    """
    Genera el archivo index.html con todos los feeds.
    Tema oscuro con color de fondo #1f1f28
    """
    total_embeds = sum(f['total_embeds'] for f in feeds)
    total_bandcamp = sum(f['bandcamp'] for f in feeds)
    total_youtube = sum(f['youtube'] for f in feeds)
    total_soundcloud = sum(f['soundcloud'] for f in feeds)

    # Ordenar feeds por nombre
    feeds_sorted = sorted(feeds, key=lambda x: x['name'])

    # Generar tarjetas de feeds
    feeds_html = ""
    for feed in feeds_sorted:
        latest_info = ""
        if feed['latest_date']:
            latest_info = f"<div class='feed-date'>📅 Última actualización: {escape(feed['latest_date'])}</div>"

        feeds_html += f"""
        <div class="feed-card">
            <h3 class="feed-title">{escape(feed['name'])}</h3>
            <div class="feed-stats">
                <div class="stat-item">
                    <span class="stat-number">{feed['total_embeds']}</span>
                    <span class="stat-label">Total</span>
                </div>
                <div class="stat-item">
                    <span class="stat-icon">🎵</span>
                    <span class="stat-number">{feed['bandcamp']}</span>
                </div>
                <div class="stat-item">
                    <span class="stat-icon">📺</span>
                    <span class="stat-number">{feed['youtube']}</span>
                </div>
                <div class="stat-item">
                    <span class="stat-icon">🔊</span>
                    <span class="stat-number">{feed['soundcloud']}</span>
                </div>
                <div class="stat-item">
                    <span class="stat-number">{feed['pages']}</span>
                    <span class="stat-label">páginas</span>
                </div>
            </div>
            {latest_info}
            <a href="{escape(feed['html_file'])}" class="feed-link">Ver embeds →</a>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FreshRSS Embeds - Índice</title>
    <link rel="icon" type="image/png" href="images/rss.png">
    <link rel="stylesheet" href="theme-palettes.css">

    <style>
        [data-theme="og"], :root:not([data-theme]) {{
            --bg: #1f1f28;
            --surface: #2a2a37;
            --surface-2: #16161d;
            --border: #54546d;
            --text: #dcd7ba;
            --text-muted: #938aa9;
            --accent: #7e9cd8;
            --accent-2: #957fb8;
            --success: #76946a;
            --warning: #c8c093;
            --danger: #e46876;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: var(--bg);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: var(--surface);
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
        }}

        header {{
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 30px;
            border-bottom: 3px solid var(--accent);
        }}

        h1 {{
            font-size: 3em;
            color: var(--text);
            margin-bottom: 10px;
        }}

        .subtitle {{
            font-size: 1.2em;
            color: var(--text-muted);
            margin-bottom: 20px;
        }}

        .global-stats {{
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-top: 20px;
            flex-wrap: wrap;
        }}

        .global-stat {{
            background: linear-gradient(135deg, var(--accent) 0%, var(--accent-2) 100%);
            color: var(--bg);
            padding: 20px 30px;
            border-radius: 15px;
            font-weight: 600;
            box-shadow: 0 4px 15px rgba(126, 156, 216, 0.4);
        }}

        .global-stat-number {{
            font-size: 2em;
            display: block;
            margin-bottom: 5px;
        }}

        .global-stat-label {{
            font-size: 0.9em;
            opacity: 0.9;
        }}

        .search-box {{
            margin: 30px 0;
            text-align: center;
        }}

        .search-input {{
            width: 100%;
            max-width: 600px;
            padding: 15px 25px;
            font-size: 1.1em;
            border: 2px solid var(--border);
            background: var(--surface-2);
            color: var(--text);
            border-radius: 50px;
            outline: none;
            transition: all 0.3s;
        }}

        .search-input:focus {{
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(126, 156, 216, 0.2);
        }}

        .search-input::placeholder {{
            color: var(--text-muted);
        }}

        .feeds-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 25px;
            margin-top: 30px;
        }}

        .feed-card {{
            background: var(--surface-2);
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            transition: all 0.3s;
            display: flex;
            flex-direction: column;
            /* Sin esto, un grid item no encoge por debajo del ancho de su
               contenido (min-width: auto por defecto) y una palabra larga
               en el título fuerza scroll horizontal en pantallas estrechas. */
            min-width: 0;
        }}

        .feed-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 15px rgba(0,0,0,0.4);
        }}

        .feed-title {{
            font-size: 1.5em;
            color: var(--text);
            margin-bottom: 15px;
            word-wrap: break-word;
        }}

        .feed-stats {{
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 10px;
            margin-bottom: 15px;
        }}

        .stat-item {{
            text-align: center;
            padding: 10px;
            background: var(--surface);
            border-radius: 8px;
        }}

        .stat-icon {{
            font-size: 1.5em;
            display: block;
            margin-bottom: 5px;
        }}

        .stat-number {{
            font-size: 1.3em;
            font-weight: bold;
            color: var(--accent);
            display: block;
        }}

        .stat-label {{
            font-size: 0.8em;
            color: var(--text-muted);
            display: block;
            margin-top: 2px;
        }}

        .feed-date {{
            font-size: 0.9em;
            color: var(--text-muted);
            margin-bottom: 15px;
        }}

        .feed-link {{
            display: inline-block;
            background: linear-gradient(135deg, var(--accent) 0%, var(--accent-2) 100%);
            color: var(--bg);
            padding: 12px 30px;
            border-radius: 25px;
            text-decoration: none;
            font-weight: 600;
            text-align: center;
            transition: all 0.3s;
            margin-top: auto;
        }}

        .feed-link:hover {{
            transform: scale(1.05);
            box-shadow: 0 5px 15px rgba(126, 156, 216, 0.4);
        }}

        .no-results {{
            text-align: center;
            padding: 60px 20px;
            color: var(--text-muted);
            font-size: 1.2em;
        }}

        .tools-link {{
            text-align: center;
            margin: 30px 0;
        }}

        .tools-link a {{
            display: inline-block;
            background: var(--border);
            color: var(--text);
            padding: 15px 30px;
            border-radius: 12px;
            text-decoration: none;
            font-weight: 600;
            transition: all 0.3s;
        }}

        .tools-link a:hover {{
            background: #625e7f;
            transform: translateY(-2px);
        }}

        footer {{
            text-align: center;
            margin-top: 50px;
            padding-top: 30px;
            border-top: 2px solid var(--border);
            color: var(--text-muted);
        }}

        footer a {{
            color: var(--accent);
            text-decoration: none;
        }}

        footer a:hover {{
            text-decoration: underline;
        }}

        @keyframes spin {{
            from {{ transform: rotate(0deg); }}
            to {{ transform: rotate(360deg); }}
        }}

        /* Botón de actualización flotante */
        #update-btn {{
            position: fixed;
            bottom: 30px;
            right: 30px;
            background: linear-gradient(135deg, var(--accent) 0%, var(--accent-2) 100%);
            color: var(--bg);
            border: none;
            padding: 14px 22px;
            border-radius: 50px;
            font-size: 1em;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 20px rgba(126, 156, 216, 0.5);
            transition: all 0.3s;
            z-index: 1000;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        #update-btn:hover:not(:disabled) {{
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(126, 156, 216, 0.7);
        }}

        #update-btn:disabled {{
            opacity: 0.6;
            cursor: not-allowed;
        }}

        #update-toast {{
            position: fixed;
            bottom: 90px;
            right: 30px;
            background: var(--surface);
            color: var(--text);
            padding: 12px 20px;
            border-radius: 10px;
            font-size: 0.9em;
            box-shadow: 0 4px 15px rgba(0,0,0,0.4);
            opacity: 0;
            transform: translateY(10px);
            transition: all 0.3s;
            pointer-events: none;
            max-width: 280px;
            border-left: 4px solid var(--accent);
            z-index: 1001;
        }}

        #update-toast.show {{
            opacity: 1;
            transform: translateY(0);
        }}

        #update-toast.error {{
            border-left-color: var(--danger);
        }}

        @media (max-width: 768px) {{
            body {{
                padding: 12px;
            }}

            .feeds-grid {{
                grid-template-columns: 1fr;
                gap: 16px;
            }}

            h1 {{
                font-size: 2em;
            }}

            .container {{
                padding: 20px;
            }}

            .global-stats {{
                gap: 15px;
            }}

            .global-stat {{
                padding: 14px 20px;
            }}

            .feed-stats {{
                grid-template-columns: repeat(3, 1fr);
            }}

            .feed-link,
            .tools-link a,
            #update-btn {{
                min-height: 44px;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
        }}

        @media (max-width: 480px) {{
            body {{
                padding: 8px;
            }}

            .container {{
                padding: 14px;
                border-radius: 12px;
            }}

            h1 {{
                font-size: 1.5em;
            }}

            .subtitle {{
                font-size: 1em;
            }}

            .global-stat {{
                padding: 10px 16px;
            }}

            .global-stat-number {{
                font-size: 1.5em;
            }}

            .feed-stats {{
                grid-template-columns: repeat(2, 1fr);
            }}

            .feed-card {{
                padding: 16px;
            }}

            #update-btn {{
                bottom: 16px;
                right: 16px;
                padding: 12px 18px;
            }}

            #update-toast {{
                bottom: 76px;
                right: 16px;
                left: 16px;
                max-width: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎵 FreshRSS Embeds</h1>
            <p class="subtitle">Colección de música de tus feeds RSS</p>

            <div class="global-stats">
                <div class="global-stat">
                    <span class="global-stat-number">{len(feeds)}</span>
                    <span class="global-stat-label">Feeds</span>
                </div>
                <div class="global-stat">
                    <span class="global-stat-number">{total_embeds}</span>
                    <span class="global-stat-label">Total embeds</span>
                </div>
                <div class="global-stat">
                    <span class="global-stat-number">🎵 {total_bandcamp}</span>
                    <span class="global-stat-label">Bandcamp</span>
                </div>
                <div class="global-stat">
                    <span class="global-stat-number">📺 {total_youtube}</span>
                    <span class="global-stat-label">YouTube</span>
                </div>
                <div class="global-stat">
                    <span class="global-stat-number">🔊 {total_soundcloud}</span>
                    <span class="global-stat-label">SoundCloud</span>
                </div>
            </div>
        </header>

        <div class="tools-link">
            <a href="sync_tools_freshrss.html">🔧 Herramientas de Sincronización</a>
        </div>

        <div class="search-box">
            <input type="text"
                   id="search"
                   class="search-input"
                   placeholder="🔍 Buscar feeds..."
                   onkeyup="filterFeeds()">
        </div>

        <div class="feeds-grid" id="feeds-grid">
            {feeds_html}
        </div>

        <div id="no-results" class="no-results" style="display: none;">
            No se encontraron feeds que coincidan con tu búsqueda.
        </div>

        <footer>
            <p>Generado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p style="margin-top: 10px;">
                FreshRSS Embed Generator | Tema oscuro #1f1f28
            </p>
        </footer>
    </div>

    <button id="update-btn" onclick="triggerUpdate()">
        <span id="update-icon">&#x21bb;</span>
        <span id="update-label">Actualizar</span>
    </button>
    <div id="update-toast"></div>

    <script>
        function showToast(msg, isError) {{
            const t = document.getElementById('update-toast');
            t.textContent = msg;
            t.className = 'show' + (isError ? ' error' : '');
            clearTimeout(t._timer);
            t._timer = setTimeout(() => t.className = '', 4000);
        }}

        function setUpdating(active) {{
            const btn = document.getElementById('update-btn');
            const icon = document.getElementById('update-icon');
            const label = document.getElementById('update-label');
            btn.disabled = active;
            if (active) {{
                icon.style.animation = 'spin 1s linear infinite';
                label.textContent = 'Actualizando...';
            }} else {{
                icon.style.animation = '';
                label.textContent = 'Actualizar';
            }}
        }}

        function pollStatus() {{
            fetch('/api/status')
                .then(r => r.json())
                .then(s => {{
                    if (s.running) {{
                        setUpdating(true);
                        setTimeout(pollStatus, 2000);
                    }} else {{
                        setUpdating(false);
                        if (s.last_error) {{
                            showToast('Error: ' + s.last_error, true);
                        }} else if (s.last_update) {{
                            showToast('Actualizado correctamente. Recarga la pagina.');
                            setTimeout(() => location.reload(), 2500);
                        }}
                    }}
                }})
                .catch(() => setTimeout(pollStatus, 3000));
        }}

        function triggerUpdate() {{
            setUpdating(true);
            showToast('Iniciando actualizacion...');
            fetch('/api/update', {{ method: 'POST' }})
                .then(r => {{
                    if (r.status === 409) {{
                        showToast('Ya hay una actualizacion en curso.');
                        pollStatus();
                    }} else if (r.ok) {{
                        pollStatus();
                    }} else {{
                        showToast('Error al iniciar la actualizacion.', true);
                        setUpdating(false);
                    }}
                }})
                .catch(() => {{
                    showToast('No se pudo conectar con el servidor.', true);
                    setUpdating(false);
                }});
        }}

        // Comprobar si hay actualizacion en curso al cargar
        fetch('/api/status')
            .then(r => r.json())
            .then(s => {{ if (s.running) {{ setUpdating(true); pollStatus(); }} }})
            .catch(() => {{}});

        function filterFeeds() {{
            const searchTerm = document.getElementById('search').value.toLowerCase();
            const feedCards = document.querySelectorAll('.feed-card');
            const noResults = document.getElementById('no-results');
            let visibleCount = 0;

            feedCards.forEach(card => {{
                const title = card.querySelector('.feed-title').textContent.toLowerCase();
                if (title.includes(searchTerm)) {{
                    card.style.display = 'flex';
                    visibleCount++;
                }} else {{
                    card.style.display = 'none';
                }}
            }});

            if (visibleCount === 0) {{
                noResults.style.display = 'block';
            }} else {{
                noResults.style.display = 'none';
            }}
        }}
    </script>
    <script src="theme-picker.js"></script>
    <script src="settings-panel.js"></script>
</body>
</html>
"""

    index_path = os.path.join(output_dir, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return index_path


def main():
    parser = argparse.ArgumentParser(
        description='Genera un index.html para los embeds de FreshRSS (VERSIÓN TEMA OSCURO)'
    )

    parser.add_argument('--input-dir', default='freshrss_embeds',
                       help='Directorio con los embeds de FreshRSS (default: freshrss_embeds)')

    args = parser.parse_args()

    print("\n" + "="*80)
    print("📑 GENERADOR DE ÍNDICE - FreshRSS Embeds")
    print("="*80 + "\n")

    # Escanear directorio
    feeds = scan_embeds_directory(args.input_dir)

    if not feeds:
        print("\n✗ No se encontraron feeds en el directorio")
        print(f"   Asegúrate de que {args.input_dir} contenga archivos HTML generados")
        return

    # Generar índice
    print(f"\n{'='*80}")
    print("📝 GENERANDO ÍNDICE")
    print(f"{'='*80}\n")

    index_path = generate_index_html(feeds, args.input_dir)

    print(f"\n{'='*80}")
    print("✅ ÍNDICE GENERADO")
    print(f"{'='*80}")
    print(f"📄 Archivo: {index_path}")
    print(f"📊 Total de feeds: {len(feeds)}")
    print(f"🎵 Total de embeds: {sum(f['total_embeds'] for f in feeds)}")
    print(f"\n🌐 Abre el archivo en tu navegador para ver el índice")
    print(f"🎨 Tema oscuro: #1f1f28")
    print(f"{'='*80}\n")


if __name__ == '__main__':
    main()
