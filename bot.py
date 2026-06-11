import asyncio
import httpx
import os
from datetime import datetime
from telegram import Bot

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = -499821637
MESSAGE_ID = 12
API_URL = "https://worldcup26.ir/get/games"

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

def get_live_match(games):
    for g in games:
        if g["finished"] == "FALSE" and g["time_elapsed"] not in ("notstarted", "null", ""):
            return g
    return None

def format_widget(games):
    match = get_live_match(games)
    if not match:
        return None
    home = match["home_team_name_en"]
    away = match["away_team_name_en"]
    hf = FLAGS.get(home, "🏳️")
    af = FLAGS.get(away, "🏳️")
    hs = match["home_score"]
    aws = match["away_score"]
    minute = match["time_elapsed"]
    minute_display = "En vivo" if minute == "live" else f"{minute}'"
    return f"{hf} {hs} — {aws} {af} · {minute_display}"

async def main():
    bot = Bot(token=TOKEN)
    print("Widget iniciado. Solo activo durante partidos en vivo...")
    while True:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(API_URL)
                data = resp.json()
            games = data.get("games", [])
            texto = format_widget(games)
            if texto:
                await bot.edit_message_text(
                    chat_id=CHAT_ID,
                    message_id=MESSAGE_ID,
                    text=texto,
                    parse_mode="Markdown"
                )
                print(f"🔴 {texto}")
            else:
                print(f"ℹ️ Sin partido en vivo — {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            if "not modified" in str(e).lower():
                print(f"ℹ️ Sin cambios a las {datetime.now().strftime('%H:%M:%S')}")
            else:
                print(f"⚠️ Error: {e}")
        await asyncio.sleep(20)

asyncio.run(main())
