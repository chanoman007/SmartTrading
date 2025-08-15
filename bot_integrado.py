# bot_integrado_final_CONTEXTUAL.py
# Bucle principal para análisis técnico + IA/override + envío a Telegram.
# Integra antiflood_utils.py para evitar señales repetidas por tiempo/% precio.
# Respeta contratos de archivos compartidos y config.json con recarga dinámica.
# Logs: [CFG], 🔍, 📊, 🤖, 📩, ⏳, 🔼, ✅, ❌

import json
import os
import time
import math
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple

import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv
load_dotenv()
resumen_histeresis = []  # Acumulador global de señales por ciclo


# === Antiflood (usa tu módulo local) ===
try:
    import antiflood_utils as AF  # debe existir en el mismo directorio
except Exception:
    AF = None

# ========================
# Utilidades de configuración y símbolos
# ========================

def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _cargar_config_seguro() -> Dict[str, Any]:
    try:
        cfg = _load_json("config.json")
        print("[CFG] Config cargada desde config.json", flush=True)
        return cfg
    except Exception as e:
        print(f"❌ Error cargando config.json: {e}", flush=True)
        return {}

def _leer_filtered() -> Tuple[List[str], str]:
    try:
        data = _load_json("simbolos_filtrados.json")
        gen = data.get("generated_at")
        if not gen:
            return None, None
        dt = datetime.fromisoformat(gen.replace("Z", "+00:00"))
        age_min = (datetime.now(timezone.utc) - dt).total_seconds() / 60.0
        if age_min <= 70 and data.get("symbols"):
            return data["symbols"], "filtered"
        return None, None
    except Exception:
        return None, None

def _obtener_simbolos_y_origen(cfg: Dict[str, Any]) -> Tuple[List[str], str]:
    s, origen = _leer_filtered()
    if s:
        return s, origen
    fallback = cfg.get("simbolos") or []
    if not isinstance(fallback, list):
        fallback = []
    return list(fallback), "config"

def _espera_siguiente_ciclo(inicio_ts: float, cfg: Dict[str, Any]) -> None:
    freq = int(cfg.get("frecuencia_segundos", 60))
    dur = max(0, time.time() - inicio_ts)
    wait = max(1, freq - int(dur))
    print(f"⏳ Esperando {wait}s para próximo ciclo…", flush=True)
    time.sleep(wait)

# ========================
# Datos de mercado (Binance REST público)
# ========================

BINANCE_API = "https://api.binance.com"

def _klines(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    url = f"{BINANCE_API}/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    cols = ["open_time","open","high","low","close","volume","close_time","qav","trades","taker_base","taker_quote","ignore"]
    df = pd.DataFrame(data, columns=cols)
    for col in ["open","high","low","close","volume","qav","taker_base","taker_quote"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df[["open_time","open","high","low","close","volume","close_time"]]

# ========================
# Indicadores técnicos (sin TA-Lib)
# ========================

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)
    roll_up = pd.Series(up, index=close.index).ewm(span=period, adjust=False).mean()
    roll_down = pd.Series(down, index=close.index).ewm(span=period, adjust=False).mean()
    rs = roll_up / (roll_down + 1e-12)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - macd_signal
    return macd, macd_signal, hist

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=1).mean()
    return atr

def _volume_relative(volume: pd.Series, period: int = 20) -> pd.Series:
    ma = volume.rolling(window=period, min_periods=1).mean()
    vr = volume / (ma + 1e-12)
    return vr

# ========================
# Análisis + decisión IA/override
# ========================

def _analisis_tecnico(df: pd.DataFrame, cfg: Dict[str, Any]) -> Dict[str, Any]:
    ind = cfg.get("indicadores", {}) if isinstance(cfg.get("indicadores", {}), dict) else {}
    rsi_p = int(ind.get("rsi_period", 14))
    macd_fast = int(ind.get("macd_fast", 12))
    macd_slow = int(ind.get("macd_slow", 26))
    macd_signal = int(ind.get("macd_signal", 9))
    ema_s = int(ind.get("ema_short_period", 20))
    ema_l = int(ind.get("ema_long_period", 50))
    atr_p = int(ind.get("atr_period", 14))
    vr_p = int(ind.get("volume_relative_period", 20))

    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]

    rsi_val = _rsi(close, rsi_p).iloc[-1]
    macd_line, macd_sig, _ = _macd(close, macd_fast, macd_slow, macd_signal)
    macd_val = macd_line.iloc[-1] - macd_sig.iloc[-1]
    ema_short = _ema(close, ema_s).iloc[-1]
    ema_long = _ema(close, ema_l).iloc[-1]
    atr_val = _atr(high, low, close, atr_p).iloc[-1]
    atr_pct = float(atr_val / (close.iloc[-1] + 1e-12)) * 100.0
    vol_rel = _volume_relative(vol, vr_p).iloc[-1]

    confluencias = 0
    if rsi_val > 50: confluencias += 1
    if macd_val > 0: confluencias += 1
    if ema_short > ema_long: confluencias += 1
    fuerza = "Débil"
    if confluencias >= 2:
        fuerza = "Media"
    if confluencias == 3:
        fuerza = "Fuerte"

    return {
        "precio_actual": float(close.iloc[-1]),
        "rsi": float(rsi_val),
        "macd": float(macd_val),
        "ema_short": float(ema_short),
        "ema_long": float(ema_long),
        "atr_pct": round(atr_pct, 2),
        "volumen_rel": float(vol_rel),
        "fuerza": fuerza,
        "patron": "Ninguno"
    }

def _ia_simulada(simbolo: str, at: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    precio = at["precio_actual"]
    rango_pct = max(0.1, min(0.5, at["atr_pct"] / 100.0 * 0.4))
    rango = [round(precio * (1 - rango_pct), 6), round(precio * (1 + rango_pct), 6)]
    sl = round(precio * (1 - max(0.01, at["atr_pct"]/100.0)), 6)
    tp = round(precio * (1 + max(0.02, at["atr_pct"]/100.0 * 1.6)), 6)
    trailing = 3  # % base

    base_conf = 25
    if at["fuerza"] == "Media":
        base_conf = 45
    elif at["fuerza"] == "Fuerte":
        base_conf = 65

    veredicto = "Sí" if base_conf >= int(cfg.get("min_confiabilidad_media", 30)) else "No"
    mensaje = (
        f"Análisis IA de {simbolo}:\n"
        f"- Fuerza: {at['fuerza']}\n"
        f"- RSI: {at['rsi']:.2f} | MACD: {at['macd']:.5f}\n"
        f"- Vol Rel: {at['volumen_rel']:.2f} | ATR%: {at['atr_pct']:.2f}\n"
        f"- Rango sugerido: {rango[0]} – {rango[1]}\n"
        f"- SL: {sl} | TP: {tp} | Trailing: {trailing}%\n"
        f"Veredicto: {veredicto}"
    )
    return {
        "veredicto": veredicto,
        "confiabilidad": base_conf,
        "rango": rango,
        "sl": sl,
        "tp": tp,
        "trailing": trailing,
        "mensaje": mensaje
    }

def _ia_real_groq(simbolo: str, at: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        print("🤖 GROQ_API_KEY no configurada. Usando IA simulada.", flush=True)
        return _ia_simulada(simbolo, at, cfg)
    try:
        prompt = (
            f"Analiza {simbolo} con estos datos: "
            f"precio={at['precio_actual']}, rsi={at['rsi']:.2f}, macd={at['macd']:.5f}, "
            f"atr_pct={at['atr_pct']:.2f}, vol_rel={at['volumen_rel']:.2f}, fuerza={at['fuerza']}. "
            f"Devuelve JSON con veredicto('Sí'|'No'), confiabilidad(0-100), rango[float,float], sl, tp, trailing(%) y mensaje."
        )
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {
            "model": "llama-3.1-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        }
        r = requests.post(url, headers=headers, json=body, timeout=30)
        if r.status_code != 200:
            print(f"🤖 IA real falló ({r.status_code}). Usando simulada.", flush=True)
            return _ia_simulada(simbolo, at, cfg)
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        import re, json as _json
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            print("🤖 IA real sin JSON parseable. Usando simulada.", flush=True)
            return _ia_simulada(simbolo, at, cfg)
        parsed = _json.loads(m.group(0))
        for k in ["veredicto","confiabilidad","rango","sl","tp","trailing","mensaje"]:
            if k not in parsed:
                print("🤖 IA real JSON incompleto. Usando simulada.", flush=True)
                return _ia_simulada(simbolo, at, cfg)

             # ⚠️ Parche: si devuelve números redondos como 65.0 o 70.0, le agregamos pequeño ruido decimal
        try:
            conf_raw = float(parsed["confiabilidad"])
            if conf_raw == int(conf_raw):
                import random
                ruido = random.uniform(-0.4, 0.4)
                nuevo_valor = round(conf_raw + ruido, 2)
                parsed["confiabilidad"] = nuevo_valor
                print(f"🎯 Confianza IA redonda detectada: {conf_raw:.2f} → Modificada a: {nuevo_valor:.2f}", flush=True)
            else:
                print(f"✅ Confianza IA ya con decimales: {conf_raw:.2f}", flush=True)
        except Exception as e:
            print(f"⚠️ Error aplicando parche de redondeo: {e}", flush=True)
        return parsed

    except Exception as e:
        print(f"🤖 Excepción IA real: {e}. Usando simulada.", flush=True)
        return _ia_simulada(simbolo, at, cfg)

def _aplicar_override(simbolo: str, at: Dict[str, Any], ia: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], bool, bool]:
    permitir = bool(cfg.get("permitir_override_en_rango", True))
    if not permitir:
        return ia, False, False

    precio = at["precio_actual"]
    rango = ia.get("rango") or [precio * 0.98, precio * 1.02]
    desviacion_max = float(cfg.get("desviacion_maxima_rango", 0.25))  # fracción
    dentro = (precio >= rango[0] * (1 - desviacion_max)) and (precio <= rango[1] * (1 + desviacion_max))

    override_conf_min = int(cfg.get("override_conf_min", 20))
    override_min_vol_rel = float(cfg.get("override_min_vol_rel", 0.9))
    override_min_rsi = float(cfg.get("override_min_rsi", 45))
    condiciones_ok = (at["volumen_rel"] >= override_min_vol_rel) and (at["rsi"] >= override_min_rsi)
    disparador = (ia.get("veredicto") == "No") or (int(ia.get("confiabilidad", 0)) < override_conf_min)

    if disparador and dentro and condiciones_ok:
        ia2 = dict(ia)
        ia2["veredicto"] = "Sí"
        ia2["mensaje"] = "🚨 ALTO RIESGO (Override en rango activado)\n" + ia.get("mensaje", "")
        return ia2, True, True
    return ia, False, False

def _clasificar_fuerza_conf(confiabilidad: float, cfg: Dict[str, Any]) -> str:
    f = "Débil"
    if confiabilidad >= int(cfg.get("min_confiabilidad_media", 30)):
        f = "Media"
    if confiabilidad >= int(cfg.get("min_confiabilidad_fuerte", 60)):
        f = "Fuerte"
    return f

def _construir_payload(simbolo: str, at: Dict[str, Any], ia: Dict[str, Any], override_aplicado: bool, alto_riesgo: bool, cfg: Dict[str, Any]) -> Dict[str, Any]:
    # Nuevo cálculo de confiabilidad dinámico
    pesos = cfg.get("pesos", {})
    histeresis = cfg.get("histeresis_confianza", 1.0)

    rsi = at["rsi"]
    macd = at["macd"]
    ema_short = at["ema_short"]
    ema_long = at["ema_long"]
    volumen_rel = at["volumen_rel"]
    atr_pct = at["atr_pct"]
    patron = at.get("patron", "Ninguno")

    
    confianza = float(ia.get("confiabilidad", 0))
    penalizacion = 0

    if rsi < 40 or rsi > 80:
        penalizacion += pesos.get("rsi_extremo", 0)

    if macd < 0:
        penalizacion += pesos.get("macd_bajista", 0)

    if ema_short < ema_long:
        penalizacion += pesos.get("ema_bajista", 0)

    if volumen_rel < 0.8:
        penalizacion += pesos.get("volumen_bajo", 0)

    if atr_pct < 0.15:
        penalizacion += pesos.get("atr_bajo", 0)

    if patron == "Ninguno":
        penalizacion += pesos.get("sin_patron", 0)

    confianza -= penalizacion
    confianza = max(0, round(confianza, 2))

    print(f"🧠 Confianza IA original: {ia.get('confiabilidad', 0)}%", flush=True)
    print(f"⚙️ Penalización total: {penalizacion} → Confianza final: {confianza}%", flush=True)



    # Continúa la función original
    fuerza_por_conf = _clasificar_fuerza_conf(confianza, cfg)
    payload = {
        "simbolo": simbolo,
        "precio_actual": at["precio_actual"],
        "rsi": round(at["rsi"], 2),
        "macd": round(at["macd"], 5),
        "fuerza": at["fuerza"],
        "fuerza_por_conf": fuerza_por_conf,
        "confiabilidad": min(confianza, 100),
        "rango": ia.get("rango"),
        "sl": ia.get("sl"),
        "tp": ia.get("tp"),
        "trailing": ia.get("trailing"),
        "mensaje_ia": ia.get("mensaje"),
        "override": override_aplicado,
        "alto_riesgo": alto_riesgo,
        "timestamp": int(time.time() * 1000),
        "modo_simulacion": os.getenv("USE_FAKE_IA", "true").lower() == "true",
        "volumen_rel": round(at["volumen_rel"], 2),
        "atr_pct": round(at["atr_pct"], 2),
        "monto_usdt": float(cfg.get("monto_inversion_usdt", 5.0))
    }
    return payload


# ========================
# Envío Telegram / integración existente
# ========================

def _enviar_por_telegram(simbolo: str, payload: Dict[str, Any]) -> None:
    try:
        import enviar_interactivo
        enviar_interactivo.enviar_mensaje_con_botones(
    simbolo,
    payload['precio_actual'],
    payload['fuerza'],
    payload['confiabilidad'],
    payload['rsi'],
    payload['macd'],
    payload['volumen_rel'],
    payload['atr_pct'],
    payload['rango'],
    payload['sl'],
    payload['tp'],
    payload['trailing'],
    payload['monto_usdt'],
    mensaje_ia=payload.get("mensaje_ia")
)
        print(f"📩 Enviada señal a Telegram para {simbolo}", flush=True)
    except Exception as e:
        print(f"❌ Error enviando a Telegram para {simbolo}: {e}", flush=True)
        traceback.print_exc()
        try:
            print("—— Señal (fallback consola) ——", flush=True)
            print(json.dumps({"simbolo": simbolo, **payload}, ensure_ascii=False, indent=2), flush=True)
        except Exception:
            pass

# ========================
# Procesamiento de un símbolo (E2E)
# ========================

def _procesar_un_simbolo(simbolo: str, cfg: Dict[str, Any]) -> None:
    try:
        print(f"🔍 Analizando {simbolo}…", flush=True)
        intervalo = cfg.get("intervalo", "1m")
        df = _klines(simbolo, intervalo, limit=200)
        if df is None or df.empty:
            print(f"❌ {simbolo}: sin datos de velas", flush=True)
            return

        at = _analisis_tecnico(df, cfg)
        print(f"📊 {simbolo} AT: {at}", flush=True)

        # IA: real o simulada
        use_fake = os.getenv("USE_FAKE_IA", "true").lower() == "true"
        ia = _ia_simulada(simbolo, at, cfg) if use_fake else _ia_real_groq(simbolo, at, cfg)
        print(f"🤖 {simbolo} IA: veredicto={ia.get('veredicto')} conf={float(ia.get('confiabilidad')):.1f}%", flush=True)

        ia_final, override_aplicado, alto_riesgo = _aplicar_override(simbolo, at, ia, cfg)

        # Filtro final por fuerza mínima
        fuerza_min = str(cfg.get("fuerza_minima", "Débil"))
        histeresis = float(cfg.get("histeresis_confianza", 0))

        conf = float(ia_final.get("confiabilidad", 0))
        conf_fuerte = float(cfg.get("min_confiabilidad_fuerte", 70))
        conf_media = float(cfg.get("min_confiabilidad_media", 50))

        # Clasificación ajustada por histeresis
        fuerza_por_conf = "Débil"
        if conf >= conf_media - histeresis:
            fuerza_por_conf = "Media"
        if conf >= conf_fuerte - histeresis:
            fuerza_por_conf = "Fuerte"

        niveles = {"Débil": 1, "Media": 2, "Fuerte": 3}
        if niveles.get(fuerza_por_conf, 1) < niveles.get(fuerza_min, 1):
            print(f"ℹ️  {simbolo}: Señal descartada por fuerza mínima ({fuerza_por_conf} < {fuerza_min}).", flush=True)
            return
        print(f"[DEBUG] Confianza final bruta: {conf}")
        resumen_histeresis.append(
        f"🔍 {simbolo}: Conf={conf:.2f} → Fuerza='{fuerza_por_conf}' → ❌ DESCARTADA"
        )

        if ia_final.get("veredicto") != "Sí":
            print(f"ℹ️  {simbolo}: Veredicto final IA = No. No se envía.", flush=True)
            return

        # ===== Antiflood (tu módulo) =====
        if AF:
            try:
                # Overrides desde config.json (opcionales)
                if "antiflood_cambio_precio_pct" in cfg:
                    AF.UMBRAL_VARIACION = float(cfg["antiflood_cambio_precio_pct"]) / 100.0
                if "antiflood_minutos" in cfg:
                    AF.TIEMPO_MIN_ENTRE_SEÑALES = int(cfg["antiflood_minutos"])

                historial = AF.cargar_historial()
                usar_por_intervalo = bool(cfg.get("antiflood_por_intervalo", True))
                clave = f"{simbolo}|{intervalo}" if usar_por_intervalo else simbolo

                fuerza_ref = fuerza_por_conf  # estable
                if AF.es_repetida(clave, at["precio_actual"], fuerza_ref, historial):
                    print(f"ℹ️  {simbolo}: antiflood activo (repetida). No se envía.", flush=True)
                    return
            except Exception as e:
                print(f"ℹ️  Antiflood deshabilitado por excepción: {e}", flush=True)
        # =================================

        payload = _construir_payload(simbolo, at, ia_final, override_aplicado, alto_riesgo, cfg)
        
        from utils import deberia_enviar_senal
        ok, meta = deberia_enviar_senal(payload, cfg)
        if not ok:
            print(f"📛 Señal descartada: {meta['motivo']}  [{simbolo}]")
            return
        _enviar_por_telegram(simbolo, payload)
        resumen_histeresis.append(
            f"🔍 {simbolo}: Conf={conf:.2f} → Fuerza='{fuerza_por_conf}' → ✅ ACEPTADA"
        )

        # Registrar en historial después de enviar
        if AF:
            try:
                # Ya usamos el historial cargado previamente
                usar_por_intervalo = bool(cfg.get("antiflood_por_intervalo", True))
                clave = f"{simbolo}|{intervalo}" if usar_por_intervalo else simbolo
                AF.registrar_senal(clave, at["precio_actual"], fuerza_por_conf, historial)
                AF.guardar_historial(historial)
            except Exception as e:
                print(f"ℹ️  No se pudo registrar en historial antiflood: {e}", flush=True)

    except Exception as e:
        print(f"❌ {simbolo}: {e}", flush=True)
        traceback.print_exc()

# ========================
# LOOP PRINCIPAL
# ========================

def start_loop():
    print("🚀 Bot integrado (análisis+IA+envío + antiflood) iniciado…", flush=True)
    while True:
        ciclo_inicio = time.time()
        try:
            cfg = _cargar_config_seguro()
            simbolos, origen = _obtener_simbolos_y_origen(cfg)
            if not simbolos:
                print("[CFG] Sin símbolos (filtered vencido y config vacía). Reintentando…", flush=True)
                time.sleep(15)
                continue

            print(f"[CFG] Usando símbolos {origen} ({len(simbolos)})", flush=True)
            print({
                "intervalo": cfg.get("intervalo", "1m"),
                "lista_simbolos": simbolos,
                "origen_simbolos": origen
            }, flush=True)

            for simbolo in simbolos:
                _procesar_un_simbolo(simbolo, cfg)

        except KeyboardInterrupt:
            print("🛑 Interrumpido por usuario.", flush=True)
            break
        except Exception as e:
            print(f"❌ Error en ciclo principal: {e}", flush=True)
            traceback.print_exc()

        _espera_siguiente_ciclo(ciclo_inicio, cfg)

        if resumen_histeresis:
            print("\n🚀 Evaluando señales con histeresis activada:")
            for r in resumen_histeresis:
                print(r)
            resumen_histeresis.clear()


if __name__ == "__main__":
    start_loop()