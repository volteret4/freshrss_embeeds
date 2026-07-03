# FreshRSS Embed Generator

Script para extraer enlaces de **Bandcamp**, **YouTube** y **SoundCloud** desde feeds de FreshRSS y generar páginas HTML con los embeds correspondientes.

## Características

- Extrae enlaces de Bandcamp, YouTube y SoundCloud
- Se conecta a FreshRSS mediante la API de Google Reader
- Procesa feeds individuales o categorías completas
- Opción de procesar solo artículos no leídos
- Genera un HTML por cada feed/categoría con todos los embeds
- Paginación con lazy loading: solo carga la página actual, las demás bajo demanda
- Interfaz web moderna y responsive con tema oscuro
- Navegación con teclado (flechas izquierda/derecha)

---

## Despliegue como servidor web

Esta sección cubre cómo exponer el sitio con SSL usando SWAG (Docker) y actualizaciones automáticas semanales.

### Requisitos

- Python virtualenv en `~/Scripts/python_venv` con Flask instalado
- SWAG corriendo en Docker con tus certificados SSL
- systemd disponible en el servidor

### 1. Clonar el repositorio

```bash
git clone <url-del-repo> ~/gits/freshrss_embeeds
cd ~/gits/freshrss_embeeds
```

### 2. Instalar dependencias en el virtualenv

```bash
~/Scripts/python_venv/bin/pip install flask requests
```

### 3. Crear el archivo de credenciales

```bash
cp .env.example .env
```

Edita `.env` con tus datos reales:

```ini
FRESHRSS_SERVER=https://rss.tudominio.com
FRESHRSS_USER=tu_usuario
FRESHRSS_PASS=tu_contraseña
FRESHRSS_FEEDS=Ambientblog,Ban Ban Ton Ton,Depósito sonoro,Lost Turntable
UPDATE_INTERVAL_DAYS=7
PORT=8765
```

El archivo `.env` está en `.gitignore` y nunca se sube al repositorio.

### 4. Generar el sitio por primera vez

```bash
cd ~/gits/freshrss_embeeds

~/Scripts/python_venv/bin/python freshrss_html_generator.py \
  --server https://rss.tudominio.com \
  --username tu_usuario \
  --password tu_contraseña \
  --unread-only \
  --max-articles 0 \
  --output-dir docs \
  --feeds "Ambientblog" "Ban Ban Ton Ton" "Depósito sonoro" "Lost Turntable"

~/Scripts/python_venv/bin/python freshrss_html_index.py --input-dir docs
```

Esto genera los HTML en `docs/` incluyendo el botón de actualización manual.

### 5. Instalar el servicio systemd

```bash
sudo cp freshrss-embeeds.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now freshrss-embeeds
```

Verificar que está corriendo:

```bash
sudo systemctl status freshrss-embeeds
journalctl -u freshrss-embeeds -f
```

El servidor queda escuchando en `http://0.0.0.0:8765` y se reinicia solo si falla.

### 6. Configurar SWAG

Edita `nginx-freshrss-embeeds.conf` y cambia la IP del servidor:

```nginx
set $upstream_app 192.168.1.100;  # IP donde corre serve.py
set $upstream_port 8765;
```

Copia la configuración al directorio de proxy-confs de SWAG:

```bash
# Ajusta la ruta según tu instalación de SWAG
cp nginx-freshrss-embeeds.conf /ruta/a/swag/config/nginx/proxy-confs/freshrss-embeeds.subdomain.conf
```

Recarga SWAG:

```bash
docker exec swag nginx -s reload
```

El archivo incluye dos opciones comentadas:
- **Opción A** (activa): subdominio `embeds.tudominio.com`
- **Opción B** (comentada): subfolder `tudominio.com/embeds/`

### Botón de actualización manual

El `index.html` generado incluye un botón flotante en la esquina inferior derecha. Al pulsarlo:

1. Llama a `/api/update` en el servidor Flask
2. El icono gira mientras la actualización está en curso
3. Al terminar recarga la página automáticamente
4. Muestra un mensaje de error si algo falla

### Actualización automática

El servidor actualiza el contenido automáticamente cada 7 días (configurable con `UPDATE_INTERVAL_DAYS` en `.env`). No es necesario ningún cron job externo.

Para comprobar cuándo será la próxima actualización:

```bash
curl http://localhost:8765/api/status
```

---

## Uso de los scripts por separado

### Requisitos (sin servidor)

```bash
pip install requests
```

### Generador de feeds

```bash
# Listar feeds disponibles
python freshrss_html_generator.py \
  --server https://rss.tudominio.com \
  --username tu_usuario \
  --list-feeds

# Generar HTMLs de feeds específicos
python freshrss_html_generator.py \
  --server https://rss.tudominio.com \
  --username tu_usuario \
  --feeds "Ambientblog" "Lost Turntable" \
  --unread-only \
  --output-dir docs
```

### Generador de índice

```bash
python freshrss_html_index.py --input-dir docs
```

Genera `docs/index.html` con estadísticas globales, buscador y tarjetas navegables para cada feed.

### Opciones del generador

| Opción | Descripción |
|---|---|
| `--server URL` | URL del servidor FreshRSS |
| `--username USER` | Usuario de FreshRSS |
| `--password PASS` | Contraseña |
| `--feeds NOMBRES` | Nombres de feeds a procesar |
| `--categories NOMBRES` | Nombres de categorías a procesar |
| `--unread-only` | Solo artículos no leídos |
| `--max-articles N` | Máximo de artículos (0 = todos) |
| `--output-dir DIR` | Directorio de salida (default: docs) |
| `--items-per-page N` | Embeds por página (default: 8) |
| `--list-feeds` | Lista los feeds disponibles y sale |
| `--list-categories` | Lista las categorías disponibles y sale |

---

## Servicios soportados

**Bandcamp** — detecta URLs de álbumes y tracks, genera embeds interactivos.

**YouTube** — soporta `youtube.com/watch?v=ID` y `youtu.be/ID`.

**SoundCloud** — detecta URLs de tracks y genera el player embebido.

---

## Estructura del directorio

```
freshrss_embeeds/
├── serve.py                        # Servidor Flask con scheduler semanal
├── freshrss_html_generator.py      # Genera HTMLs por feed
├── freshrss_html_index.py          # Genera index.html con botón de actualización
├── freshrss-embeeds.service        # Servicio systemd
├── nginx-freshrss-embeeds.conf     # Config SWAG
├── .env                            # Credenciales (NO subir al repo)
├── .env.example                    # Plantilla de credenciales
└── docs/
    ├── index.html                  # Índice generado
    ├── Ambientblog.html
    └── ...
```

---

## Solución de problemas

**El servicio no arranca:**
```bash
journalctl -u freshrss-embeeds -n 50
```
Comprueba que `.env` existe y que `FRESHRSS_PASS` está configurado.

**Error de autenticación en FreshRSS:**
- Verifica que la API de Google Reader esté habilitada en FreshRSS
- No uses autenticación OAuth, solo usuario/contraseña nativos

**SWAG no hace proxy:**
- Confirma que la IP en `nginx-freshrss-embeeds.conf` es accesible desde el contenedor SWAG
- Si SWAG está en Docker y serve.py en el host, prueba con `172.17.0.1` como IP
- Comprueba los logs: `docker logs swag`

**El botón de actualización no aparece:**
- Regenera el índice: `python freshrss_html_index.py --input-dir docs`
- El botón solo funciona cuando se sirve desde `serve.py`, no abriendo el HTML directamente

---

## Licencia

Script de uso libre. Úsalo y modifícalo como necesites.
