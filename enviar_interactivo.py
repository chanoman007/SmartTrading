import json
import time
from pathlib import Path
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import telebot
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID"))
bot = telebot.TeleBot(TOKEN)

ORDENES_PATH = Path("ordenes_pendientes.json")

def enviar_mensaje_con_botones(
    simbolo,
    precio_actual,
    fuerza,
    confiabilidad,
    rsi,
    macd,
    vol_rel,
    atr_pct,
    rango,
    sl,
    tp,
    trailing_pct,
    monto_usdt,
    mensaje_ia=None
):
    id_orden = f"{simbolo}_{int(time.time() * 1000)}"

    mensaje = f"""📡 *Señal detectada* para *{simbolo}*

*Fuerza:* {fuerza}
*Confianza:* {float(confiabilidad):.1f}%{" ⚠️ *ALTO RIESGO*" if confiabilidad >= 95 and fuerza.lower().startswith("débil") else ""}
*RSI:* {float(rsi):.2f} | *MACD:* {float(macd):.5f}
*Volumen Rel:* {float(vol_rel):.2f} | *ATR%:* {float(atr_pct):.2f}
*Entrada:* {rango}
*Stop Loss:* {sl}
*Take Profit:* {tp}
*Trailing:* {trailing_pct}%
*Monto:* {monto_usdt} USDT
*Precio actual:* {precio_actual}"""

    if mensaje_ia:
        mensaje += f"\n\n🧠 *IA:*\n{mensaje_ia}"

    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("✅ Confirmar", callback_data=id_orden),
        InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")
    )

    payload = {
        "id": id_orden,
        "simbolo": simbolo,
        "precio_actual": precio_actual,
        "fuerza": fuerza,
        "confiabilidad": float(confiabilidad),
        "rsi": float(rsi),
        "macd": float(macd),
        "volumen_rel": float(vol_rel),
        "atr_pct": float(atr_pct),
        "rango_sugerido": rango,
        "sl": float(sl),
        "tp": float(tp),
        "trailing_pct": float(trailing_pct),
        "monto": float(monto_usdt),
        "mensaje_ia": mensaje_ia
    }

    ordenes = {}
    if ORDENES_PATH.exists():
        try:
            ordenes = json.loads(ORDENES_PATH.read_text(encoding="utf-8"))
        except Exception:
            ordenes = {}

    ordenes[id_orden] = payload
    ORDENES_PATH.write_text(json.dumps(ordenes, indent=2, ensure_ascii=False), encoding="utf-8")

    bot.send_message(CHAT_ID, mensaje, parse_mode="Markdown", reply_markup=markup)
    print(f"📩 Enviada señal a Telegram para {simbolo} (ID: {id_orden})")
