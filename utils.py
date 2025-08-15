import os
import json
import time
import traceback
from typing import Dict, Any, List, Optional
from pathlib import Path
import requests
from binance.client import Client
from datetime import datetime
import numpy as np
import pandas as pd

# -------------------------------
# FUNCIONES DASHBOARD
# -------------------------------

def validar_y_reparar_dashboard():
    try:
        ruta = Path("Dashboard/data.js")
        if not ruta.exists():
            print("📁 No existe data.js, creando desde cero.")
            ruta.write_text("const operaciones = [];", encoding="utf-8")
            return

        contenido = ruta.read_text(encoding="utf-8").strip()
        if not contenido.startswith("const operaciones ="):
            print("⚠️ data.js no comienza con la declaración esperada. Se reescribirá.")
            ruta.write_text("const operaciones = [];", encoding="utf-8")
            return

        inicio = contenido.find("[")
        fin = contenido.rfind("]") + 1
        if inicio == -1 or fin == -1:
            print("⚠️ Estructura de array inválida en data.js. Reinicializando.")
            ruta.write_text("const operaciones = [];", encoding="utf-8")
            return

        json_raw = contenido[inicio:fin]
        json.loads(json_raw)  # Valida

        print("✅ data.js está correctamente formado.")
    except Exception as e:
        print(f"❌ data.js corrupto. Se reescribirá vacío. Error: {e}")
        ruta.write_text("const operaciones = [];", encoding="utf-8")

def _append_operacion_dashboard(simbolo: str, payload: Dict[str, Any]):
    try:
        ruta = Path("Dashboard/data.js")
        if not ruta.exists():
            ruta.write_text("const operaciones = [];", encoding="utf-8")

        contenido = ruta.read_text(encoding="utf-8").strip()
        inicio = contenido.find("[")
        fin = contenido.rfind("]") + 1

        if inicio == -1 or fin == -1:
            print("⚠️ Estructura inválida en data.js. Reinicializando.")
            operaciones = []
        else:
            json_raw = contenido[inicio:fin]
            try:
                operaciones = json.loads(json_raw)
            except Exception as e:
                print(f"⚠️ Error parseando data.js: {e}. Reinicializando.")
                operaciones = []

        operaciones.append(payload)

        nuevo_contenido = "const operaciones = " + json.dumps(operaciones, indent=2, ensure_ascii=False) + ";"
        ruta.write_text(nuevo_contenido, encoding="utf-8")

    except Exception as e:
        print(f"❌ Error al escribir en dashboard: {e}")
def obtener_precio_actual(simbolo: str) -> Optional[float]:
    try:
        client = Client(os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET"))
        precio = client.get_symbol_ticker(symbol=simbolo)["price"]
        return float(precio)
    except Exception as e:
        print(f"❌ Error obteniendo precio para {simbolo}: {e}")
        return None

def redondear_qty(cantidad: float, step: float) -> float:
    precision = int(round(-1 * (step.as_integer_ratio()[1]).bit_length() / 3.321928094887362, 0))
    return round(cantidad - (cantidad % step), max(0, precision))

def cargar_config() -> Dict[str, Any]:
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

def calcular_rangos_tecnicos(df: pd.DataFrame, config: Dict[str, Any]) -> Dict[str, float]:
    rsi = df["rsi"].iloc[-1]
    macd = df["macd"].iloc[-1]
    atr_pct = df["atr_pct"].iloc[-1]
    volumen_rel = df["volumen_rel"].iloc[-1]
    fuerza = df["fuerza"].iloc[-1]
    patron = df["patron"].iloc[-1]
    precio_actual = df["close"].iloc[-1]

    return {
        "precio_actual": precio_actual,
        "rsi": rsi,
        "macd": macd,
        "atr_pct": atr_pct,
        "volumen_rel": volumen_rel,
        "fuerza": fuerza,
        "patron": patron
    }

def es_senal_repetida(simbolo: str, historial: Dict[str, Any], precio_actual: float, config: Dict[str, Any]) -> bool:
    if simbolo not in historial:
        return False
    ultima = historial[simbolo]
    if config.get("antiflood_por_intervalo", True) and ultima["intervalo"] != config["intervalo"]:
        return False
    tiempo_actual = time.time()
    tiempo_ultima = ultima["timestamp"]
    if tiempo_actual - tiempo_ultima < config.get("antiflood_minutos", 10) * 60:
        dif = abs(precio_actual - ultima["precio"]) / ultima["precio"] * 100
        if dif < config.get("antiflood_cambio_precio_pct", 0.5):
            return True
    return False

def guardar_historial_senal(simbolo: str, intervalo: str, precio_actual: float):
    try:
        path = Path("historial_senales.json")
        if not path.exists():
            path.write_text("{}", encoding="utf-8")
        data = json.loads(path.read_text(encoding="utf-8"))
        data[simbolo] = {
            "timestamp": time.time(),
            "intervalo": intervalo,
            "precio": precio_actual
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"❌ Error guardando historial de señal: {e}")
def cargar_historial_senales() -> Dict[str, Any]:
    try:
        path = Path("historial_senales.json")
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Error leyendo historial de señales: {e}")
        return {}

def log_debug(texto: str):
    print(f"[DEBUG] {texto}", flush=True)

def normalizar_confianza(conf: float) -> float:
    return round(float(conf), 2)

def calcular_trailing_stop(precio_entrada: float, porcentaje: float) -> float:
    return round(precio_entrada * (1 - porcentaje / 100), 6)

def calcular_take_profit(precio_entrada: float, porcentaje: float) -> float:
    return round(precio_entrada * (1 + porcentaje / 100), 6)

def calcular_stop_loss(precio_entrada: float, porcentaje: float) -> float:
    return round(precio_entrada * (1 - porcentaje / 100), 6)

def generar_id_unico(simbolo: str) -> str:
    import random, string
    sufijo = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    timestamp = int(time.time())
    return f"{simbolo}_{timestamp}_{sufijo}"

# === FILTRO FINAL DE SEÑALES POR FUERZA Y CONFIABILIDAD ===

_FUERZA_RANK = {"Débil": 1, "Debil": 1, "D": 1, "Media": 2, "M": 2, "Fuerte": 3, "F": 3}

def _norm_fuerza(fuerza: str) -> str:
    if not fuerza:
        return "Débil"
    f = fuerza.strip().lower()
    if f.startswith("fuer"): return "Fuerte"
    if f.startswith("med"): return "Media"
    return "Débil"

def _rank_fuerza(fuerza: str) -> int:
    return _FUERZA_RANK.get(_norm_fuerza(fuerza), 1)

def _min_conf_por_fuerza(cfg: dict, fuerza_norm: str) -> float:
    if fuerza_norm == "Fuerte":
        return float(cfg.get("min_confiabilidad_fuerte", 65.0))
    if fuerza_norm == "Media":
        return float(cfg.get("min_confiabilidad_media", 60.0))
    return float(cfg.get("min_confiabilidad_debil", 999.0))

def _hay_inconsistencia_grave(fuerza_norm: str, confianza: float) -> bool:
    return fuerza_norm == "Débil" and confianza >= 95.0

def _pasa_histeresis(conf_actual: float, conf_min: float, cfg: dict) -> bool:
    margen = float(cfg.get("histeresis_confianza", 0.0))
    return (conf_actual + margen) >= conf_min

def deberia_enviar_senal(payload: dict, cfg: dict) -> tuple[bool, dict]:
    meta = {"motivo": "OK", "override": False, "alto_riesgo": False, "inconsistencia": False}
    fuerza_norm = _norm_fuerza(payload.get("fuerza", ""))
    conf = float(payload.get("confiabilidad", 0.0))
    fuerza_min_norm = _norm_fuerza(cfg.get("fuerza_minima", "Media"))

    if _rank_fuerza(fuerza_norm) < _rank_fuerza(fuerza_min_norm):
        meta["motivo"] = f"Fuerza {fuerza_norm} < mínima {fuerza_min_norm}"
        return False, meta

    conf_min = _min_conf_por_fuerza(cfg, fuerza_norm)
    if not _pasa_histeresis(conf, conf_min, cfg):
        meta["motivo"] = f"Confianza {conf:.2f} < mínimo {conf_min:.2f}"
        return False, meta

    if _hay_inconsistencia_grave(fuerza_norm, conf):
        meta["motivo"] = "Inconsistencia: Débil con confianza alta"
        meta["inconsistencia"] = True
        return False, meta

    return True, meta
