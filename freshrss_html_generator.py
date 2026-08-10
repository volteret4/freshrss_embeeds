#!/usr/bin/env python3
"""
Script para generar HTML con embeds de Bandcamp, YouTube y SoundCloud
desde feeds de FreshRSS.

VERSIÓN CORREGIDA:
1. Corregido el problema de feeds que generaban HTML iguales
2. Corregido unread_only para que funcione correctamente
3. Corregido el manejo de IDs de feeds
4. Cada feed ahora genera su propio HTML independiente
5. Mejorado el procesamiento de nombres de feeds
"""

import os
import re
import json
import argparse
import getpass
import requests
import urllib.request
import urllib.error
import time
from pathlib import Path

import freshrss_db
from html import escape
from collections import defaultdict
from urllib.parse import urlparse, parse_qs
from datetime import datetime


class FreshRSSConfig:
    """Configuración para conexión a FreshRSS"""
    def __init__(self, server_url, username, password):
        self.server_url = server_url.rstrip('/')
        self.username = username
        self.password = password
        self.api_url = f"{self.server_url}/api/greader.php"
        self.token = None


class FreshRSSClient:
    """Cliente para interactuar con la API de FreshRSS (Google Reader API)"""

    def __init__(self, config):
        self.config = config
        self.session = requests.Session()

    def authenticate(self):
        """Autentica con FreshRSS y obtiene el token"""
        print(f"🔌 Conectando a {self.config.server_url}...")

        # Paso 1: Obtener el token de autenticación
        auth_url = f"{self.config.api_url}/accounts/ClientLogin"
        auth_data = {
            'Email': self.config.username,
            'Passwd': self.config.password
        }

        try:
            response = self.session.post(auth_url, data=auth_data)
            response.raise_for_status()

            # Extraer el token de la respuesta
            for line in response.text.split('\n'):
                if line.startswith('Auth='):
                    self.config.token = line.split('=', 1)[1]
                    break

            if not self.config.token:
                raise Exception("No se pudo obtener el token de autenticación")

            print("✅ Autenticación exitosa\n")
            return True

        except requests.exceptions.RequestException as e:
            print(f"❌ Error de autenticación: {e}")
            return False

    def get_feeds(self):
        """Obtiene la lista de feeds disponibles"""
        url = f"{self.config.api_url}/reader/api/0/subscription/list"
        headers = {'Authorization': f'GoogleLogin auth={self.config.token}'}
        params = {'output': 'json'}

        try:
            response = self.session.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            feeds = []
            for subscription in data.get('subscriptions', []):
                feed = {
                    'id': subscription.get('id', ''),
                    'title': subscription.get('title', ''),
                    'categories': [cat.get('label', '') for cat in subscription.get('categories', [])]
                }
                feeds.append(feed)

            return feeds

        except Exception as e:
            print(f"❌ Error obteniendo feeds: {e}")
            return []

    def get_categories(self):
        """Obtiene la lista de categorías disponibles"""
        url = f"{self.config.api_url}/reader/api/0/tag/list"
        headers = {'Authorization': f'GoogleLogin auth={self.config.token}'}
        params = {'output': 'json'}

        try:
            response = self.session.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            categories = []
            for tag in data.get('tags', []):
                if tag.get('id', '').startswith('user/-/label/'):
                    label = tag.get('id', '').split('user/-/label/')[-1]
                    categories.append(label)

            return categories

        except Exception as e:
            print(f"❌ Error obteniendo categorías: {e}")
            return []

    def get_articles(self, feed_id=None, category=None, count=100, unread_only=False):
        """
        Obtiene artículos de un feed o categoría específica.
        CORREGIDO: Ahora maneja correctamente unread_only
        """
        url = f"{self.config.api_url}/reader/api/0/stream/contents"
        headers = {'Authorization': f'GoogleLogin auth={self.config.token}'}

        params = {'output': 'json'}

        # count=0 significa "sin límite" (así lo llama serve.py en la
        # actualización diaria: --max-articles 0). Sin este caso especial,
        # count*10 y el slice [:count] de más abajo se quedan en 0 y la API
        # nunca devuelve nada -- por eso la web dejó de traer artículos
        # nuevos pese a que el cron corría bien todos los días.
        unlimited = count <= 0
        request_n = 1000 if unlimited else count
        if unread_only:
            params['n'] = request_n * 10  # Multiplicar por 10 para asegurar suficientes no leídos
        else:
            params['n'] = request_n

        if feed_id:
            params['s'] = feed_id
        elif category:
            params['s'] = f'user/-/label/{category}'
        else:
            params['s'] = 'user/-/state/com.google/reading-list'

        # CORREGIDO: Para solo no leídos, excluir los leídos
        if unread_only:
            params['xt'] = 'user/-/state/com.google/read'

        try:
            response = self.session.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            articles = []
            for item in data.get('items', []):
                article = {
                    'id': item.get('id', ''),
                    'title': item.get('title', ''),
                    'link': item.get('alternate', [{}])[0].get('href', '') if item.get('alternate') else '',
                    'content': item.get('summary', {}).get('content', ''),
                    'published': item.get('published', 0),
                    'author': item.get('author', ''),
                    'feed_title': item.get('origin', {}).get('title', ''),
                    'feed_id': item.get('origin', {}).get('streamId', '')
                }
                articles.append(article)

            # CORREGIDO: Limitar después de filtrar
            if not articles:
                return []
            return articles if unlimited else articles[:count]

        except requests.exceptions.RequestException as e:
            print(f"❌ Error obteniendo artículos: {e}")
            print(f"   URL: {url}")
            print(f"   Parámetros: {params}")
            return []
        except Exception as e:
            print(f"❌ Error inesperado obteniendo artículos: {e}")
            return []


def fetch_bandcamp_embed_from_html(html_content):
    """
    Extrae el código embed del contenido HTML de una página de Bandcamp.
    """
    try:
        # MÉTODO 1: Buscar en el bloque TralbumData
        tralbum_data_match = re.search(
            r'var\s+TralbumData\s*=\s*(\{.+?\});',
            html_content,
            re.DOTALL
        )

        if tralbum_data_match:
            try:
                tralbum_json_str = tralbum_data_match.group(1)

                # Buscar album_id
                album_id_match = re.search(r'"?album_id"?\s*:\s*(\d+)', tralbum_json_str)
                if album_id_match:
                    album_id = album_id_match.group(1)
                    print(f"       ✅ album_id encontrado en TralbumData: {album_id}")
                    embed_url = f'https://bandcamp.com/EmbeddedPlayer/album={album_id}/size=large/bgcol=1f1f28/linkcol=9a64ff/tracklist=false/artwork=small/transparent=true/'
                    return f'<iframe style="border: 0; width: 400px; height: 120px;" src="{embed_url}" seamless></iframe>'

                # Buscar track_id si es un track
                item_type_match = re.search(r'"?item_type"?\s*:\s*"?(track|album)"?', tralbum_json_str)
                if item_type_match and item_type_match.group(1) == 'track':
                    track_id_match = re.search(r'"?id"?\s*:\s*(\d+)', tralbum_json_str)
                    if track_id_match:
                        track_id = track_id_match.group(1)
                        print(f"       ✅ track_id encontrado en TralbumData: {track_id}")
                        embed_url = f'https://bandcamp.com/EmbeddedPlayer/track={track_id}/size=large/bgcol=1f1f28/linkcol=9a64ff/tracklist=false/artwork=small/transparent=true/'
                        return f'<iframe style="border: 0; width: 400px; height: 120px;" src="{embed_url}" seamless></iframe>'
            except Exception as e:
                print(f"       ⚠️ Error en TralbumData: {e}")

        # MÉTODO 2: Buscar en EmbedData
        embed_data_match = re.search(
            r'var\s+EmbedData\s*=\s*(\{.+?\});',
            html_content,
            re.DOTALL
        )

        if embed_data_match:
            try:
                embed_json_str = embed_data_match.group(1)

                album_id_match = re.search(r'"?album_id"?\s*:\s*(\d+)', embed_json_str)
                if album_id_match:
                    album_id = album_id_match.group(1)
                    print(f"       ✅ album_id encontrado en EmbedData: {album_id}")
                    embed_url = f'https://bandcamp.com/EmbeddedPlayer/album={album_id}/size=large/bgcol=1f1f28/linkcol=9a64ff/tracklist=false/artwork=small/transparent=true/'
                    return f'<iframe style="border: 0; width: 400px; height: 120px;" src="{embed_url}" seamless></iframe>'

                track_id_match = re.search(r'"?track_id"?\s*:\s*(\d+)', embed_json_str)
                if track_id_match:
                    track_id = track_id_match.group(1)
                    print(f"       ✅ track_id encontrado en EmbedData: {track_id}")
                    embed_url = f'https://bandcamp.com/EmbeddedPlayer/track={track_id}/size=large/bgcol=1f1f28/linkcol=9a64ff/tracklist=false/artwork=small/transparent=true/'
                    return f'<iframe style="border: 0; width: 400px; height: 120px;" src="{embed_url}" seamless></iframe>'
            except Exception as e:
                print(f"       ⚠️ Error en EmbedData: {e}")

        # MÉTODO 3: Buscar directamente en el HTML
        album_id_patterns = [
            r'data-band-id="(\d+)".*?data-item-id="(\d+)".*?data-item-type="album"',
            r'"?album_id"?\s*:\s*(\d+)',
            r'album[=/](\d{8,12})',
        ]

        for pattern in album_id_patterns:
            match = re.search(pattern, html_content, re.DOTALL)
            if match:
                album_id = match.group(2) if len(match.groups()) > 1 else match.group(1)
                print(f"       ✅ album_id encontrado (búsqueda general): {album_id}")
                embed_url = f'https://bandcamp.com/EmbeddedPlayer/album={album_id}/size=large/bgcol=1f1f28/linkcol=9a64ff/tracklist=false/artwork=small/transparent=true/'
                return f'<iframe style="border: 0; width: 400px; height: 120px;" src="{embed_url}" seamless></iframe>'

        # Buscar track_id
        track_id_patterns = [
            r'data-band-id="(\d+)".*?data-item-id="(\d+)".*?data-item-type="track"',
            r'"?track_id"?\s*:\s*(\d+)',
            r'track[=/](\d{8,12})',
        ]

        for pattern in track_id_patterns:
            match = re.search(pattern, html_content, re.DOTALL)
            if match:
                track_id = match.group(2) if len(match.groups()) > 1 else match.group(1)
                print(f"       ✅ track_id encontrado (búsqueda general): {track_id}")
                embed_url = f'https://bandcamp.com/EmbeddedPlayer/track={track_id}/size=large/bgcol=1f1f28/linkcol=9a64ff/tracklist=false/artwork=small/transparent=true/'
                return f'<iframe style="border: 0; width: 400px; height: 120px;" src="{embed_url}" seamless></iframe>'

        # MÉTODO 4: Buscar el iframe embed directo
        iframe_match = re.search(
            r'<iframe[^>]*src=["\']([^"\']*EmbeddedPlayer[^"\']*)["\']',
            html_content,
            re.IGNORECASE
        )
        if iframe_match:
            embed_url = iframe_match.group(1)
            if embed_url.startswith('//'):
                embed_url = 'https:' + embed_url
            # Cambiar el bgcol al tema oscuro
            embed_url = re.sub(r'bgcol=[0-9a-fA-F]+', 'bgcol=1f1f28', embed_url)
            print(f"       ✅ iframe embed encontrado directamente")
            return f'<iframe style="border: 0; width: 400px; height: 120px;" src="{embed_url}" seamless></iframe>'

        print(f"       ❌ No se encontró embed en ningún método")
        return None

    except Exception as e:
        print(f"       ❌ Error extrayendo embed: {e}")
        return None


def get_bandcamp_embed(url, retry_count=3):
    """
    Obtiene el código embed de Bandcamp para una URL dada.
    """
    for attempt in range(retry_count):
        try:
            if attempt > 0:
                print(f"       🔄 Reintento {attempt + 1}/{retry_count}...")
                time.sleep(2)

            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
            )

            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', errors='ignore')
                print(f"       ✅ Página descargada (código {response.status})")

            embed = fetch_bandcamp_embed_from_html(html)

            if embed:
                return embed
            else:
                print(f"       ⚠️ No se encontró embed en intento {attempt + 1}")

        except urllib.error.HTTPError as e:
            print(f"       ❌ Error HTTP {e.code}: {e.reason}")
            if e.code == 404:
                print(f"       ℹ️ La página no existe (404)")
                return None
            elif e.code >= 500:
                print(f"       ℹ️ Error del servidor, reintentando...")
        except urllib.error.URLError as e:
            print(f"       ❌ Error de conexión: {e.reason}")
        except Exception as e:
            print(f"       ❌ Error inesperado: {type(e).__name__}: {e}")

    print(f"       ❌ Falló después de {retry_count} intentos")
    return None


def extract_bandcamp_url(text):
    """Extrae URLs de Bandcamp del texto"""
    patterns = [
        r'https?://[a-zA-Z0-9-]+\.bandcamp\.com/(?:album|track)/[a-zA-Z0-9-]+',
        r'https?://bandcamp\.com/[a-zA-Z0-9-]+',
    ]

    urls = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        urls.extend(matches)

    return list(set(urls))


def extract_youtube_url(text):
    """Extrae URLs de YouTube del texto"""
    patterns = [
        r'https?://(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'https?://(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'https?://youtu\.be/([a-zA-Z0-9_-]{11})',
    ]

    video_ids = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        video_ids.extend(matches)

    # Usar youtube.com normal
    urls = [f"https://www.youtube.com/embed/{vid}" for vid in set(video_ids)]
    return urls


def extract_soundcloud_url(text):
    """Extrae URLs de SoundCloud del texto"""
    patterns = [
        r'https?://soundcloud\.com/[a-zA-Z0-9-_]+/[a-zA-Z0-9-_]+',
        r'https?://(?:w|m)\.soundcloud\.com/[a-zA-Z0-9-_]+/[a-zA-Z0-9-_]+',
    ]

    urls = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        urls.extend(matches)

    return list(set(urls))


def extract_bandcamp_id(embed_code):
    """
    Extrae el album_id o track_id del código embed de Bandcamp.
    """
    if not embed_code:
        return None

    # Buscar album=XXXXXXXX
    album_match = re.search(r'album=(\d+)', embed_code)
    if album_match:
        return f"album_{album_match.group(1)}"

    # Buscar track=XXXXXXXX
    track_match = re.search(r'track=(\d+)', embed_code)
    if track_match:
        return f"track_{track_match.group(1)}"

    return None


def process_feed(client, feed_id, feed_name, unread_only=False, max_articles=100):
    """
    Procesa un feed individual y extrae los embeds de Bandcamp, YouTube y SoundCloud.
    CORREGIDO: Ahora procesa feeds individuales correctamente.
    """
    print(f"\n{'='*80}")
    print(f"📡 Procesando feed: {feed_name}")
    print(f"   ID: {feed_id}")
    print(f"{'='*80}\n")

    # CORREGIDO: Usar el feed_id directamente
    articles = client.get_articles(feed_id=feed_id, count=max_articles, unread_only=unread_only)

    embeds = {
        'bandcamp': [],
        'youtube': [],
        'soundcloud': []
    }

    # Sets para rastrear URLs ya procesadas y evitar duplicados
    processed_bandcamp = set()
    processed_youtube = set()
    processed_soundcloud = set()

    print(f"Artículos obtenidos: {len(articles)}")
    if unread_only:
        print(f"(Solo artículos no leídos)")

    if len(articles) == 0:
        print("⚠️  ADVERTENCIA: No se obtuvieron artículos")
        print("   Posibles causas:")
        print("   - El feed está vacío")
        print("   - No hay artículos no leídos" if unread_only else "   - El feed_id es incorrecto")
        print("   - Hay un problema con la API")
        return embeds

    # Mostrar info del primer artículo
    if articles:
        first = articles[0]
        print(f"  📄 Primer artículo: {first['title'][:60]}...")
        print(f"     Contenido: {len(first['content'])} chars")
        print(f"     Link: {first['link'][:70]}...")
        print(f"     Feed origen: {first['feed_title']}")

    for i, article in enumerate(articles, 1):
        content = article['content'] + ' ' + article['link']

        # Extraer URLs de Bandcamp
        bc_urls = extract_bandcamp_url(content)
        for url in bc_urls:
            if url in processed_bandcamp:
                print(f"  [{i}/{len(articles)}] ⭐️  Bandcamp duplicado (omitido): {url}")
                continue

            processed_bandcamp.add(url)
            print(f"  [{i}/{len(articles)}] 🎵 Bandcamp encontrado: {url}")
            embed_code = get_bandcamp_embed(url)

            if embed_code:
                bandcamp_id = extract_bandcamp_id(embed_code)
                embeds['bandcamp'].append({
                    'url': url,
                    'embed': embed_code,
                    'title': article['title'],
                    'article_link': article['link'],
                    'author': article['author'],
                    'feed': article['feed_title'],
                    'date': datetime.fromtimestamp(article['published']).strftime('%Y-%m-%d %H:%M'),
                    'id': bandcamp_id
                })
                print(f"       ✅ Embed obtenido")
            else:
                print(f"       ⚠   No se pudo obtener embed")

        # Extraer URLs de YouTube
        yt_urls = extract_youtube_url(content)
        for url in yt_urls:
            if url in processed_youtube:
                print(f"  [{i}/{len(articles)}] ⭐️  YouTube duplicado (omitido): {url}")
                continue

            processed_youtube.add(url)
            print(f"  [{i}/{len(articles)}] 📺 YouTube encontrado: {url}")
            embeds['youtube'].append({
                'url': url,
                'title': article['title'],
                'article_link': article['link'],
                'author': article['author'],
                'feed': article['feed_title'],
                'date': datetime.fromtimestamp(article['published']).strftime('%Y-%m-%d %H:%M'),
                'id': url
            })

        # Extraer URLs de SoundCloud
        sc_urls = extract_soundcloud_url(content)
        for url in sc_urls:
            if url in processed_soundcloud:
                print(f"  [{i}/{len(articles)}] ⭐️  SoundCloud duplicado (omitido): {url}")
                continue

            processed_soundcloud.add(url)
            print(f"  [{i}/{len(articles)}] 🔊 SoundCloud encontrado: {url}")
            embeds['soundcloud'].append({
                'url': url,
                'title': article['title'],
                'article_link': article['link'],
                'author': article['author'],
                'feed': article['feed_title'],
                'date': datetime.fromtimestamp(article['published']).strftime('%Y-%m-%d %H:%M'),
                'id': url
            })

    total = len(embeds['bandcamp']) + len(embeds['youtube']) + len(embeds['soundcloud'])
    print(f"\n📊 Total encontrados: {total} embeds únicos")
    print(f"   Bandcamp: {len(embeds['bandcamp'])}")
    print(f"   YouTube: {len(embeds['youtube'])}")
    print(f"   SoundCloud: {len(embeds['soundcloud'])}\n")

    return embeds


def sanitize_feed_name(feed_name):
    """Convierte un nombre de feed al formato usado para archivos"""
    # Remover caracteres especiales y reemplazar espacios con guiones bajos
    safe_name = re.sub(r'[^\w\s-]', '', feed_name).strip().replace(' ', '_')
    # Limitar longitud
    if len(safe_name) > 50:
        safe_name = safe_name[:50]
    return safe_name


def _load_existing_embeds(filepath):
    """
    Recupera los embeds ya publicados en un HTML generado por esta misma
    función, leyendo el "const allPagesData = {...}" que ella misma incrusta.
    Necesario porque cada corrida solo trae los artículos NUEVOS no leídos
    (--unread-only) — sin esto, regenerar un feed con solo lo de hoy borra
    el histórico acumulado de ejecuciones anteriores.
    """
    if not os.path.exists(filepath):
        return {}
    try:
        html_text = Path(filepath).read_text(encoding="utf-8")
    except OSError:
        return {}

    marker = "const allPagesData = "
    idx = html_text.find(marker)
    if idx == -1:
        return {}
    start = idx + len(marker)
    try:
        pages_data, _ = json.JSONDecoder().raw_decode(html_text, start)
    except (json.JSONDecodeError, ValueError):
        return {}

    recovered = {}
    for embeds in pages_data.values():
        for e in embeds:
            key = e.get("id") or e.get("url")
            if key:
                recovered[key] = e
    return recovered


def generate_feed_html(feed_name, embeds, output_dir, items_per_page=8, max_pages_buttons=15):
    """
    Genera un archivo HTML con paginación para un feed específico.
    CORREGIDO: Cada feed genera su propio HTML independiente.
    """
    # Combinar todos los embeds en una sola lista
    all_embeds = []

    for bc in embeds['bandcamp']:
        all_embeds.append({
            'type': 'bandcamp',
            'url': bc['url'],
            'embed_html': bc.get('embed'),
            'title': bc['title'],
            'article_link': bc['article_link'],
            'author': bc['author'],
            'feed': bc['feed'],
            'date': bc['date'],
            'id': bc.get('id', bc['url'])
        })

    for yt in embeds['youtube']:
        all_embeds.append({
            'type': 'youtube',
            'url': yt['url'],
            'title': yt['title'],
            'article_link': yt['article_link'],
            'author': yt['author'],
            'feed': yt['feed'],
            'date': yt['date'],
            'id': yt.get('id', yt['url'])
        })

    for sc in embeds['soundcloud']:
        all_embeds.append({
            'type': 'soundcloud',
            'url': sc['url'],
            'title': sc['title'],
            'article_link': sc['article_link'],
            'author': sc['author'],
            'feed': sc['feed'],
            'date': sc['date'],
            'id': sc.get('id', sc['url'])
        })

    # CORREGIDO: Generar nombre de archivo único para cada feed
    safe_name = sanitize_feed_name(feed_name)
    main_filename = f"{safe_name}.html"

    # Fusiona con lo ya publicado en el archivo existente (ver
    # _load_existing_embeds): cada corrida solo trae los artículos NUEVOS no
    # leídos, así que sin esto se perdería el histórico acumulado.
    merged_by_id = _load_existing_embeds(os.path.join(output_dir, main_filename))
    for e in all_embeds:
        key = e.get('id') or e.get('url')
        if key:
            merged_by_id[key] = e
    all_embeds = list(merged_by_id.values())

    # Descarta los ya marcados como "escuchado/visto" en el servidor (SQLite,
    # vía /api/listened) — solo local, no toca el estado de leído en FreshRSS,
    # así que sin este filtro reaparecerían en cada regeneración.
    already_listened = freshrss_db.listened_ids()
    all_embeds = [e for e in all_embeds if e['id'] not in already_listened]

    # Ordenar por fecha (más recientes primero)
    all_embeds.sort(key=lambda x: x['date'], reverse=True)

    # Paginar
    total_items = len(all_embeds)
    total_pages = (total_items + items_per_page - 1) // items_per_page

    pages_data = {}
    for i in range(total_pages):
        start_idx = i * items_per_page
        end_idx = start_idx + items_per_page
        pages_data[str(i + 1)] = all_embeds[start_idx:end_idx]

    # Convertir a JSON para incrustar
    pages_data_json = json.dumps(pages_data, ensure_ascii=False, indent=2)

    # Nombre sanitizado para localStorage
    storage_key = safe_name

    # Generar HTML con tema oscuro #1f1f28
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(feed_name)} - Embeds</title>
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
        }}

        header {{
            text-align: center;
            margin-bottom: 40px;
        }}

        h1 {{
            color: var(--text);
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        }}

        .stats {{
            color: var(--warning);
            font-size: 1.1em;
        }}

        .embeds-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 30px;
            margin-bottom: 40px;
        }}

        @media (max-width: 768px) {{
            body {{
                padding: 12px;
            }}

            .embeds-grid {{
                grid-template-columns: 1fr;
                gap: 16px;
            }}

            header {{
                margin-bottom: 24px;
            }}

            h1 {{
                font-size: 1.8em;
                overflow-wrap: break-word;
            }}

            .embed-item {{
                padding: 16px;
            }}

            .pagination {{
                gap: 8px;
                margin: 24px 0;
            }}

            .page-btn,
            .listen-btn {{
                min-height: 44px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }}

            .page-info {{
                min-height: 44px;
                display: inline-flex;
                align-items: center;
            }}
        }}

        @media (max-width: 480px) {{
            body {{
                padding: 8px;
            }}

            h1 {{
                font-size: 1.4em;
            }}

            .stats {{
                font-size: 1em;
            }}

            .embed-item {{
                padding: 12px;
                border-radius: 8px;
            }}

            .embed-info h3 {{
                font-size: 1em;
            }}

            .page-btn {{
                padding: 10px 14px;
                font-size: 0.95em;
            }}

            .pagination {{
                gap: 6px;
            }}
        }}

        .embed-item {{
            background: var(--surface);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            transition: transform 0.3s, box-shadow 0.3s, opacity 0.3s;
            /* Sin esto, un grid item no encoge por debajo del ancho de su
               contenido (min-width: auto por defecto) y un título largo sin
               espacios fuerza scroll horizontal en pantallas estrechas. */
            min-width: 0;
        }}

        .embed-item:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 12px rgba(0,0,0,0.4);
        }}

        .embed-item.listened {{
            opacity: 0.4;
            background: var(--surface-2);
        }}

        .embed-item.listened:hover {{
            opacity: 0.6;
        }}

        .embed-info {{
            margin-bottom: 15px;
        }}

        .embed-type {{
            display: inline-block;
            font-size: 1.2em;
            margin-bottom: 8px;
        }}

        .embed-info h3 {{
            font-size: 1.1em;
            color: var(--text);
            margin-bottom: 10px;
            line-height: 1.4;
            overflow-wrap: break-word;
            word-break: break-word;
        }}

        .embed-info .meta {{
            font-size: 0.9em;
            color: var(--text-muted);
            margin-bottom: 8px;
        }}

        .embed-info a {{
            color: var(--accent);
            text-decoration: none;
            font-size: 0.9em;
        }}

        .embed-info a:hover {{
            text-decoration: underline;
            color: var(--accent-2);
        }}

        .embed-container {{
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 200px;
        }}

        .embed-container iframe {{
            max-width: 100%;
        }}

        /* Los embeds de YouTube traen width/height fijos (560x315) en el
           <iframe>; forzamos proporción 16:9 fluida para que no queden
           recortados ni deformados al encogerse en pantallas estrechas. */
        .embed-container iframe[src*="youtube"] {{
            width: 100%;
            height: auto;
            aspect-ratio: 16 / 9;
        }}

        .listen-btn {{
            margin-top: 15px;
            padding: 10px 20px;
            background: var(--accent);
            color: var(--bg);
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.95em;
            font-weight: 600;
            transition: background 0.3s, transform 0.2s;
            width: 100%;
        }}

        .listen-btn:hover {{
            background: var(--accent-2);
            transform: translateY(-2px);
        }}

        .listen-btn.listened {{
            background: var(--border);
            color: var(--text-muted);
        }}

        .listen-btn.listened:hover {{
            background: #625e7f;
        }}

        .pagination {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
            margin: 40px 0;
            flex-wrap: wrap;
        }}

        .page-btn {{
            padding: 10px 20px;
            background: var(--border);
            color: var(--text);
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            transition: background 0.3s;
        }}

        .page-btn:hover:not(:disabled) {{
            background: #625e7f;
        }}

        .page-btn:disabled {{
            background: var(--surface);
            color: var(--border);
            cursor: not-allowed;
        }}

        .page-btn.active {{
            background: var(--accent);
            color: var(--bg);
            font-weight: bold;
        }}

        .page-info {{
            padding: 10px 20px;
            background: var(--surface);
            border-radius: 8px;
            font-weight: 600;
            color: var(--warning);
        }}

        .loading {{
            text-align: center;
            padding: 40px;
            font-size: 1.2em;
            color: var(--text-muted);
        }}

        .loading::after {{
            content: '...';
            animation: dots 1.5s steps(4, end) infinite;
        }}

        @keyframes dots {{
            0%, 20% {{ content: '.'; }}
            40% {{ content: '..'; }}
            60%, 100% {{ content: '...'; }}
        }}

        footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid var(--surface);
            color: var(--text-muted);
        }}

        footer a {{
            color: var(--accent);
            text-decoration: none;
        }}

        footer a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{escape(feed_name)}</h1>
            <div class="stats">
                Total: {total_items} embeds únicos | Páginas: {total_pages}
            </div>
        </header>

        <div id="pagination-top" class="pagination"></div>
        <div id="content"></div>
        <div id="pagination-bottom" class="pagination"></div>

        <footer>
            <p>Generado desde FreshRSS (versión corregida)</p>
        </footer>
    </div>

    <script>
        // Datos incrustados directamente en el HTML
        const allPagesData = {pages_data_json};
        const totalPages = {total_pages};
        const maxPagesButtons = {max_pages_buttons};
        const feedName = '{storage_key}';
        const storageKey = `freshrss_listened_${{feedName}}`;

        let currentPage = 1;
        let listenedItems = new Set();

        // Cargar items escuchados desde localStorage
        function loadListenedItems() {{
            try {{
                const stored = localStorage.getItem(storageKey);
                if (stored) {{
                    listenedItems = new Set(JSON.parse(stored));
                    console.log(`Loaded ${{listenedItems.size}} listened items for ${{feedName}}`);
                }}
            }} catch (error) {{
                console.error('Error loading listened items:', error);
            }}
        }}

        // Guardar items escuchados en localStorage
        function saveListenedItems() {{
            try {{
                localStorage.setItem(storageKey, JSON.stringify(Array.from(listenedItems)));
                console.log(`Saved ${{listenedItems.size}} listened items for ${{feedName}}`);
            }} catch (error) {{
                console.error('Error saving listened items:', error);
            }}
        }}

        // Marcar/desmarcar item como escuchado. Solo "marcar" se persiste en
        // el servidor (SQLite, vía /api/listened) — el servidor no soporta
        // desmarcar, así que "desmarcar" aquí es solo visual/local hasta la
        // próxima regeneración.
        function toggleListened(itemId) {{
            if (listenedItems.has(itemId)) {{
                listenedItems.delete(itemId);
            }} else {{
                listenedItems.add(itemId);
                fetch('/api/listened', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{id: itemId}}),
                }}).catch(err => console.error('No se pudo guardar en el servidor:', err));
            }}
            saveListenedItems();
            loadPage(currentPage);
        }}

        function generateBandcampEmbed(item) {{
            if (item.embed_html) {{
                return item.embed_html;
            }}
            return `<p>URL de Bandcamp: <a href="${{item.url}}" target="_blank">${{item.url}}</a></p>`;
        }}

        function generateYoutubeEmbed(url) {{
            const embedUrl = url.includes('?') ? url : `${{url}}`;
            return `<iframe width="560" height="315" src="${{embedUrl}}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>`;
        }}

        function generateSoundcloudEmbed(url) {{
            const encodedUrl = encodeURIComponent(url);
            const embedUrl = `https://w.soundcloud.com/player/?url=${{encodedUrl}}&color=%23ff5500&auto_play=false&hide_related=false&show_comments=true&show_user=true&show_reposts=false&show_teaser=true`;
            return `<iframe width="100%" height="166" scrolling="no" frameborder="no" allow="autoplay" src="${{embedUrl}}"></iframe>`;
        }}

        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}

        function generateEmbedHTML(item) {{
            const typeIcons = {{
                'bandcamp': '🎵',
                'youtube': '📺',
                'soundcloud': '🔊'
            }};

            const typeNames = {{
                'bandcamp': 'Bandcamp',
                'youtube': 'YouTube',
                'soundcloud': 'SoundCloud'
            }};

            let embedCode = '';
            if (item.type === 'bandcamp') {{
                embedCode = generateBandcampEmbed(item);
            }} else if (item.type === 'youtube') {{
                embedCode = generateYoutubeEmbed(item.url);
            }} else if (item.type === 'soundcloud') {{
                embedCode = generateSoundcloudEmbed(item.url);
            }}

            const isListened = listenedItems.has(item.id);
            const listenedClass = isListened ? 'listened' : '';
            const btnText = isListened ? '✓ Escuchado' : 'Marcar como escuchado';
            const btnClass = isListened ? 'listened' : '';

            return `
                <div class="embed-item ${{listenedClass}}" data-id="${{escapeHtml(item.id)}}">
                    <div class="embed-info">
                        <div class="embed-type">${{typeIcons[item.type]}} ${{typeNames[item.type]}}</div>
                        <h3>${{escapeHtml(item.title)}}</h3>
                        <p class="meta">
                            📅 ${{item.date}}
                            ${{item.author ? ` | 👤 ${{escapeHtml(item.author)}}` : ''}}
                            ${{item.feed ? ` | 📡 ${{escapeHtml(item.feed)}}` : ''}}
                        </p>
                        <p><a href="${{escapeHtml(item.article_link)}}" target="_blank">Ver artículo original →</a></p>
                    </div>
                    <div class="embed-container">
                        ${{embedCode}}
                    </div>
                    <button class="listen-btn ${{btnClass}}" onclick="toggleListened('${{escapeHtml(item.id)}}')">
                        ${{btnText}}
                    </button>
                </div>
            `;
        }}

        function loadPage(pageNum) {{
            if (pageNum < 1 || pageNum > totalPages) return;

            const content = document.getElementById('content');
            const pageData = allPagesData[String(pageNum)];

            if (!pageData) {{
                content.innerHTML = '<div class="loading">Página no encontrada</div>';
                return;
            }}

            let html = '<div class="embeds-grid">';
            for (const item of pageData) {{
                html += generateEmbedHTML(item);
            }}
            html += '</div>';

            content.innerHTML = html;
            currentPage = pageNum;
            renderPagination();

            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}

        function renderPagination() {{
            const paginationHTML = createPaginationButtons();
            document.getElementById('pagination-top').innerHTML = paginationHTML;
            document.getElementById('pagination-bottom').innerHTML = paginationHTML;
        }}

        function createPaginationButtons() {{
            let html = '';

            if (currentPage > 1) {{
                html += `<button class="page-btn" onclick="changePage(${{currentPage - 1}})">← Anterior</button>`;
            }} else {{
                html += `<button class="page-btn" disabled>← Anterior</button>`;
            }}

            let startPage = Math.max(1, currentPage - Math.floor(maxPagesButtons / 2));
            let endPage = Math.min(totalPages, startPage + maxPagesButtons - 1);

            if (endPage - startPage < maxPagesButtons - 1) {{
                startPage = Math.max(1, endPage - maxPagesButtons + 1);
            }}

            if (startPage > 1) {{
                html += `<button class="page-btn" onclick="changePage(1)">1</button>`;
                if (startPage > 2) {{
                    html += `<span class="page-info">...</span>`;
                }}
            }}

            for (let i = startPage; i <= endPage; i++) {{
                if (i === currentPage) {{
                    html += `<button class="page-btn active">${{i}}</button>`;
                }} else {{
                    html += `<button class="page-btn" onclick="changePage(${{i}})">${{i}}</button>`;
                }}
            }}

            if (endPage < totalPages) {{
                if (endPage < totalPages - 1) {{
                    html += `<span class="page-info">...</span>`;
                }}
                html += `<button class="page-btn" onclick="changePage(${{totalPages}})">${{totalPages}}</button>`;
            }}

            if (currentPage < totalPages) {{
                html += `<button class="page-btn" onclick="changePage(${{currentPage + 1}})")>Siguiente →</button>`;
            }} else {{
                html += `<button class="page-btn" disabled>Siguiente →</button>`;
            }}

            return html;
        }}

        function changePage(pageNum) {{
            if (pageNum >= 1 && pageNum <= totalPages) {{
                loadPage(pageNum);
            }}
        }}

        loadListenedItems();
        console.log('Datos cargados:', Object.keys(allPagesData).length, 'páginas');
        loadPage(1);

        document.addEventListener('keydown', (e) => {{
            if (e.key === 'ArrowLeft') {{
                changePage(currentPage - 1);
            }} else if (e.key === 'ArrowRight') {{
                changePage(currentPage + 1);
            }}
        }});
    </script>
    <script src="theme-picker.js"></script>
    <script src="settings-panel.js"></script>
</body>
</html>
"""

    filepath = os.path.join(output_dir, main_filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"      ✅ {main_filename} generado ({total_pages} páginas)")
    return main_filename


def interactive_setup():
    """Modo interactivo para configurar la conexión a FreshRSS"""
    print("\n" + "="*80)
    print("🔧 CONFIGURACIÓN FRESHRSS")
    print("="*80 + "\n")

    print("Introduce la URL de tu servidor FreshRSS")
    print("Ejemplo: https://rss.example.com o http://localhost:8080")
    server_url = input("URL del servidor: ").strip()

    username = input("Usuario: ").strip()
    password = getpass.getpass("Contraseña: ")

    return FreshRSSConfig(server_url, username, password)


def find_feeds_by_name(feeds_list, feed_names):
    """
    NUEVA FUNCIÓN: Busca feeds por nombre en lugar de ID
    """
    found_feeds = []

    for name in feed_names:
        name_lower = name.lower()
        for feed in feeds_list:
            feed_title_lower = feed['title'].lower()
            if name_lower in feed_title_lower or feed_title_lower in name_lower:
                found_feeds.append(feed)
                print(f"  ✅ Encontrado: '{feed['title']}' (ID: {feed['id']})")
                break
        else:
            print(f"  ❌ No encontrado: '{name}'")

    return found_feeds


def main():
    parser = argparse.ArgumentParser(
        description='Genera HTML con embeds de Bandcamp, YouTube y SoundCloud desde FreshRSS (VERSIÓN CORREGIDA)'
    )

    # Opciones de conexión
    parser.add_argument('--interactive', action='store_true',
                       help='Modo interactivo para configurar la conexión')
    parser.add_argument('--server', help='URL del servidor FreshRSS')
    parser.add_argument('--username', help='Usuario de FreshRSS')
    parser.add_argument('--password', help='Contraseña')

    # Opciones de operación
    parser.add_argument('--list-feeds', action='store_true',
                       help='Listar todos los feeds disponibles y salir')
    parser.add_argument('--list-categories', action='store_true',
                       help='Listar todas las categorías disponibles y salir')
    parser.add_argument('--feeds', nargs='+',
                       help='NUEVO: Nombres de feeds a procesar (búsqueda por nombre)')
    parser.add_argument('--feed-ids', nargs='+',
                       help='IDs exactos de feeds a procesar (ej: feed/123)')
    parser.add_argument('--categories', nargs='+',
                       help='Nombres de categorías a procesar')
    parser.add_argument('--unread-only', action='store_true',
                       help='Solo procesar artículos no leídos')
    parser.add_argument('--max-articles', type=int, default=100,
                       help='Número máximo de artículos a obtener por feed (default: 100; 0 = sin límite)')

    # Opciones de salida
    parser.add_argument('--output-dir', default='docs',
                       help='Directorio de salida para los archivos HTML (default: docs)')
    parser.add_argument('--items-per-page', type=int, default=8,
                       help='Número de embeds por página (default: 8)')
    parser.add_argument('--max-pages-buttons', type=int, default=15,
                       help='Número máximo de botones de páginas a mostrar (default: 15)')

    args = parser.parse_args()

    # Configurar conexión a FreshRSS
    if args.interactive:
        config = interactive_setup()
    elif args.server and args.username:
        password = args.password
        if not password:
            password = getpass.getpass(f"Contraseña para {args.username}: ")
        config = FreshRSSConfig(args.server, args.username, password)
    else:
        print("❌ Debes usar --interactive o proporcionar --server y --username")
        print("Usa --help para ver ejemplos de uso")
        return

    # Crear cliente y autenticar
    client = FreshRSSClient(config)
    if not client.authenticate():
        print("\n❌ No se pudo autenticar con FreshRSS")
        return

    try:
        # Listar feeds si se solicita
        if args.list_feeds:
            print("\n" + "="*80)
            print("📡 FEEDS DISPONIBLES")
            print("="*80 + "\n")
            feeds = client.get_feeds()

            for i, feed in enumerate(feeds, 1):
                categories = ', '.join(feed['categories']) if feed['categories'] else 'Sin categoría'
                print(f"  {i}. {feed['title']}")
                print(f"     ID: {feed['id']}")
                print(f"     Categorías: {categories}\n")

            print(f"📊 Total: {len(feeds)} feeds")
            print("\nUsa estos nombres con --feeds o IDs exactos con --feed-ids")
            return

        # Listar categorías si se solicita
        if args.list_categories:
            print("\n" + "="*80)
            print("📂 CATEGORÍAS DISPONIBLES")
            print("="*80 + "\n")
            categories = client.get_categories()

            for i, category in enumerate(categories, 1):
                print(f"  {i}. {category}")

            print(f"\n📊 Total: {len(categories)} categorías")
            print("\nUsa estos nombres con --categories")
            return

        # CORREGIDO: Verificar que se especificaron feeds o categorías
        if not args.feeds and not args.feed_ids and not args.categories:
            print("\n❌ Debes especificar:")
            print("   --feeds <nombres> para buscar por nombre")
            print("   --feed-ids <IDs> para usar IDs exactos")
            print("   --categories <nombres> para usar categorías")
            print("   O usa --list-feeds / --list-categories para ver las opciones")
            return

        # Crear directorio de salida
        os.makedirs(args.output_dir, exist_ok=True)

        print(f"\n{'='*80}")
        print(f"📡 PROCESANDO FEEDS/CATEGORÍAS")
        print(f"{'='*80}")
        print(f"Servidor: {config.server_url}")
        print(f"Usuario: {config.username}")
        print(f"Solo no leídos: {'Sí' if args.unread_only else 'No'}")
        print(f"Máx. artículos: {args.max_articles}")
        print(f"{'='*80}\n")

        all_results = []

        # NUEVO: Procesar feeds por nombre
        if args.feeds:
            print("🔍 Buscando feeds por nombre...")
            feeds_list = client.get_feeds()
            found_feeds = find_feeds_by_name(feeds_list, args.feeds)

            for feed in found_feeds:
                embeds = process_feed(
                    client, feed['id'], feed['title'],
                    unread_only=args.unread_only,
                    max_articles=args.max_articles
                )

                total = len(embeds['bandcamp']) + len(embeds['youtube']) + len(embeds['soundcloud'])
                if total > 0:
                    all_results.append((feed['title'], embeds))
                else:
                    print(f"⚠️  Feed '{feed['title']}' no tiene embeds")

        # Procesar feeds por ID exacto
        if args.feed_ids:
            feeds_list = client.get_feeds()
            feeds_dict = {feed['id']: feed['title'] for feed in feeds_list}

            for feed_id in args.feed_ids:
                feed_name = feeds_dict.get(feed_id, feed_id)
                embeds = process_feed(
                    client, feed_id, feed_name,
                    unread_only=args.unread_only,
                    max_articles=args.max_articles
                )

                total = len(embeds['bandcamp']) + len(embeds['youtube']) + len(embeds['soundcloud'])
                if total > 0:
                    all_results.append((feed_name, embeds))

        # Procesar categorías (sin cambios)
        if args.categories:
            for category in args.categories:
                # NOTA: Necesitarías implementar process_category similar a process_feed
                print(f"⚠️  Procesamiento de categorías no implementado en esta versión")

        # Generar archivos HTML
        if all_results:
            print(f"\n{'='*80}")
            print(f"📄 GENERANDO ARCHIVOS HTML")
            print(f"{'='*80}\n")

            for name, embeds in all_results:
                print(f"  Generando {name}...")
                filename = generate_feed_html(name, embeds, args.output_dir, args.items_per_page, args.max_pages_buttons)
                total = len(embeds['bandcamp']) + len(embeds['youtube']) + len(embeds['soundcloud'])
                print(f"  Total: {total} embeds únicos\n")

            print(f"{'='*80}")
            print(f"✅ Archivos HTML generados en: {args.output_dir}")
            print(f"{'='*80}\n")
            print("🔧 CORRECCIONES APLICADAS:")
            print("   ✅ Cada feed genera su propio HTML independiente")
            print("   ✅ Corrección del parámetro unread_only")
            print("   ✅ Búsqueda de feeds por nombre")
            print("   ✅ Mejor manejo de IDs de feeds")
            print("   ✅ Eliminación de duplicados mejorada")
        else:
            print("\n⚠️   No se encontraron enlaces en los feeds especificados")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
