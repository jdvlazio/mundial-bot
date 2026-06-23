import asyncio
import time
import httpx
import os
from datetime import datetime, timezone, timedelta
from telegram import Bot

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = -499821637
MESSAGE_ID = 117

# API JSON oculta de ESPN (sin key, específica del Mundial 2026)
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
HEADERS = {"User-Agent": "Mozilla/5.0"}

COL_TZ = timezone(timedelta(hours=-5))   # Colombia (UTC-5, sin horario de verano)
GRACE = 10 * 60                          # 10 min tras el final antes de mostrar el próximo
EST_FULLTIME = 120 * 60                  # estimación de duración real (solo si el bot reinicia)

FLAGS = {
    "Mexico": "🇲🇽", "South Africa": "🇿🇦", "South Korea": "🇰🇷",
    "Czech Republic": "🇨🇿", "Canada": "🇨🇦", "Bosnia and Herzegovina": "🇧🇦",
    "United States": "🇺🇸", "Paraguay": "🇵🇾", "Haiti": "🇭🇹",
    "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Brazil": "🇧🇷", "Morocco": "🇲🇦",
    "Qatar": "🇶🇦", "Switzerland": "🇨🇭", "Australia": "🇦🇺",
    "Turkey": "🇹🇷", "Germany": "🇩🇪", "Curaçao": "🇨🇼",
    "Netherlands": "🇳🇱", "Japan": "🇯🇵", "Sweden": "🇸🇪",
    "Tunisia": "🇹🇳", "Belgium": "🇧🇪", "Egypt": "🇪🇬",
    "Iran": "🇮🇷", "New Zealand": "🇳🇿", "Spain": "🇪🇸",
    "Cape Verde": "🇨🇻", "Saudi Arabia": "🇸🇦", "Uruguay": "🇺🇾",
    "France": "🇫🇷", "Senegal": "🇸🇳", "Iraq": "🇮🇶",
    "Norway": "🇳🇴", "Argentina": "🇦🇷", "Algeria": "🇩🇿",
    "Austria": "🇦🇹", "Jordan": "🇯🇴", "Portugal": "🇵🇹",
    "Democratic Republic of the Congo": "🇨🇩", "Uzbekistan": "🇺🇿",
    "Colombia": "🇨🇴", "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Croatia": "🇭🇷",
    "Ghana": "🇬🇭", "Panama": "🇵🇦", "Ivory Coast": "🇨🇮",
    "Ecuador": "🇪🇨",
}

# ESPN a veces nombra distinto al de FLAGS -> lo normalizamos
ALIASES = {
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Korea Republic": "South Korea",
    "USA": "United States",
    "Türkiye": "Turkey", "Turkiye": "Turkey",
    "Czechia": "Czech Republic",
    "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast",
    "DR Congo": "Democratic Republic of the Congo",
    "Congo DR": "Democratic Republic of the Congo",
}


def _flag(name):
    return FLAGS.get(ALIASES.get(name, name), "🏳️")


def _kickoff(event):
    return datetime.fromisoformat(event["date"].replace("Z", "+00:00"))


def _col_time(dt_utc):
    return dt_utc.astimezone(COL_TZ).strftime("%I:%M %p").lstrip("0")


def parse_match(event):
    comp = event["competitions"][0]
    status = comp["status"]
    home = away = None
    for c in comp["competitors"]:
        if c["homeAway"] == "home":
            home = c
        else:
            away = c
    if not home or not away:
        return None
    return {
        "id": event["id"],
        "home": home["team"]["displayName"],
        "away": away["team"]["displayName"],
        "home_score": home.get("score", "0"),
        "away_score": away.get("score", "0"),
        "state": status["type"]["state"],          # pre / in / post
        "clock": status.get("displayClock", ""),
        "detail": status["type"].get("shortDetail", ""),
        "kickoff": _kickoff(event),
    }


async def fetch_matches():
    """Devuelve la lista de partidos del Mundial desde ESPN, o None si falla.

    Consulta una ventana de varios días (ayer..+3) para que, al terminar el
    último partido del día, ya tengamos cargado el siguiente.
    """
    hoy = datetime.now(timezone.utc)
    rango = f"{(hoy - timedelta(days=1)):%Y%m%d}-{(hoy + timedelta(days=3)):%Y%m%d}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(ESPN_URL, params={"dates": rango}, headers=HEADERS)
    if resp.status_code != 200:
        print(f"⚠️ ESPN respondió {resp.status_code}")
        return None
    out = []
    for e in resp.json().get("events", []):
        m = parse_match(e)
        if m:
            out.append(m)
    return out


def _score(m):
    return f"{_flag(m['home'])} {m['home_score']} — {m['away_score']} {_flag(m['away'])}"


def format_live(m):
    detail = (m["detail"] or "").lower()
    # En vivo con minuto -> "· 34'"; descanso o sin minuto -> solo marcador
    if "half" in detail or detail == "ht" or not m["clock"]:
        return _score(m)
    return f"{_score(m)} · {m['clock']}"


def format_final(m):
    return _score(m)


def format_preview(m):
    return f"{_flag(m['home'])} - {_flag(m['away'])} · {_col_time(m['kickoff'])}"


def build_text(matches, finish_times, now):
    """Arma el texto del mensaje. Soporta varios partidos en simultáneo:
    una línea por partido (en vivo, o finales recientes, o próximos)."""
    # 1) Partidos en vivo (prioridad) — todos los que estén jugándose
    live = sorted((m for m in matches if m["state"] == "in"), key=lambda m: m["kickoff"])
    if live:
        return "\n".join(format_live(m) for m in live)

    # 2) Finales recientes (dentro de la ventana de gracia) — todos
    recientes = sorted(
        (m for m in matches if m["state"] == "post"
         and m["id"] in finish_times and now - finish_times[m["id"]] < GRACE),
        key=lambda m: m["kickoff"],
    )
    if recientes:
        return "\n".join(format_final(m) for m in recientes)

    # 3) Próximo(s): el saque más cercano, y todos los que arranquen a esa misma hora
    upcoming = [m for m in matches if m["state"] == "pre"]
    if upcoming:
        proximo = min(m["kickoff"] for m in upcoming)
        simultaneos = sorted(
            (m for m in upcoming if m["kickoff"] == proximo),
            key=lambda m: (m["home"], m["away"]),
        )
        return "\n".join(format_preview(m) for m in simultaneos)

    return None


async def main():
    bot = Bot(token=TOKEN)
    finish_times = {}   # id del partido -> epoch del Full Time
    seen_live = set()   # ids vistos en vivo (para detectar el momento del final)
    print("Widget iniciado...")
    while True:
        try:
            matches = await fetch_matches()
            if matches is None:
                await asyncio.sleep(30)
                continue
            now = time.time()

            # Detectar cuándo terminó cada partido
            for m in matches:
                if m["state"] == "in":
                    seen_live.add(m["id"])
                elif m["state"] == "post" and m["id"] not in finish_times:
                    # Si lo vimos en vivo, este es el momento real del final;
                    # si el bot arrancó con el partido ya terminado, lo estimamos.
                    finish_times[m["id"]] = now if m["id"] in seen_live \
                        else m["kickoff"].timestamp() + EST_FULLTIME

            # Decidir qué mostrar (soporta varios partidos en simultáneo)
            texto = build_text(matches, finish_times, now)

            if texto:
                await bot.edit_message_text(
                    chat_id=CHAT_ID,
                    message_id=MESSAGE_ID,
                    text=texto,
                    parse_mode="Markdown"
                )
                print(f"📌 {texto}")
            else:
                print(f"ℹ️ Nada que mostrar — {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            if "not modified" in str(e).lower():
                print(f"ℹ️ Sin cambios a las {datetime.now().strftime('%H:%M:%S')}")
            else:
                print(f"⚠️ Error: {e}")
        await asyncio.sleep(30)

asyncio.run(main())
