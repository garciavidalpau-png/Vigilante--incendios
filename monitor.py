#!/usr/bin/env python3
"""
Vigilante de incendios en León.

Consulta Google News, detecta noticias NUEVAS sobre incendios en la
provincia de León y envía una notificación push al móvil vía ntfy.sh.

No necesita claves de API. Solo Python 3 estándar.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

# ----------------------- CONFIGURACIÓN -----------------------
# Nombre de tu "topic" de ntfy. Invéntate uno raro y difícil de adivinar.
# (cualquiera que conozca este nombre podría enviarte notificaciones)
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "incendios-leon-CAMBIA-ESTO-2481")

# Términos de búsqueda en Google News. Puedes afinarlos a tu gusto.
QUERY = os.environ.get("FIRE_QUERY", "incendio León")

# Si el titular/resumen contiene ALGUNA de estas palabras, se considera de León.
# Deja la lista vacía [] si no quieres filtrar.
INCLUDE_ANY = ["león", "bierzo", "leonés", "leonesa", "castilla y león",
               "bañeza", "astorga", "ponferrada", "babia", "laciana"]

# Si contiene ALGUNA de estas, se descarta (para evitar León de México, etc.)
EXCLUDE_ANY = ["guanajuato", "méxico", "mexico", "nicaragua"]

# Fichero donde se recuerda qué noticias ya se han visto.
STATE_FILE = Path(os.environ.get("STATE_FILE", "seen.json"))
MAX_REMEMBER = 500
# -------------------------------------------------------------


def google_news_rss(query):
    q = urllib.parse.quote(query)
    return (f"https://news.google.com/rss/search?q={q}"
            f"&hl=es-ES&gl=ES&ceid=ES:es")


def fetch(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (fire-monitor)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_items(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        guid = (it.findtext("guid") or link).strip()
        desc = (it.findtext("description") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        items.append({"guid": guid, "title": title, "link": link,
                      "desc": desc, "pub": pub})
    return items


def matches(item):
    text = (item["title"] + " " + item["desc"]).lower()
    if EXCLUDE_ANY and any(w in text for w in EXCLUDE_ANY):
        return False
    if INCLUDE_ANY and not any(w in text for w in INCLUDE_ANY):
        return False
    return True


def load_seen():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_seen(seen):
    STATE_FILE.write_text(
        json.dumps(seen[-MAX_REMEMBER:], ensure_ascii=False),
        encoding="utf-8")


def notify(item):
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    message = f"{item['title']}\n\n{item['link']}"
    req = urllib.request.Request(
        url,
        data=message.encode("utf-8"),
        headers={
            "Title": "Nuevo incendio en Leon",   # sin acentos: cabecera HTTP
            "Priority": "high",
            "Tags": "fire",
            "Click": item["link"],
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30).read()


def main():
    first_run = not STATE_FILE.exists()
    seen = load_seen()
    seen_set = set(seen)

    xml_bytes = fetch(google_news_rss(QUERY))
    items = parse_items(xml_bytes)

    if first_run:
        # En el primer arranque no notificamos nada: solo memorizamos lo que
        # ya existe, para avisar únicamente de lo que aparezca a partir de ahora.
        save_seen([it["guid"] for it in items])
        print(f"Primera ejecución: memorizadas {len(items)} noticias "
              f"actuales sin notificar.")
        return

    new_items = [it for it in items
                 if it["guid"] not in seen_set and matches(it)]
    new_items.reverse()  # de la más antigua a la más nueva

    for it in new_items:
        try:
            notify(it)
            print("Notificado:", it["title"])
        except Exception as e:
            print("Error al notificar:", e, file=sys.stderr)
        seen.append(it["guid"])

    save_seen(seen)
    print(f"Revisadas {len(items)} noticias, {len(new_items)} nuevas.")


if __name__ == "__main__":
    main()
