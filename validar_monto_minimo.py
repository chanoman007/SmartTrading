import json
import time
from pathlib import Path

STEP_MIN = 0.0001  # mínimo permitido de cantidad
ARCHIVO_ORDENES = Path("ordenes_pendientes.json")

def calcular_monto_minimo(precio_actual: float, step: float = STEP_MIN) -> float:
    return round(precio_actual * step, 2)

def validar_ordenes():
    if not ARCHIVO_ORDENES.exists():
        print("ℹ️ No hay archivo de órdenes pendientes.")
        return

    try:
        ordenes = json.loads(ARCHIVO_ORDENES.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Error leyendo ordenes_pendientes.json: {e}")
        return

    for orden_id, payload in ordenes.items():
        simbolo = payload.get("simbolo")
        monto = float(payload.get("monto", payload.get("monto_usdt", 0)))
        precio = float(payload.get("precio_actual", 0))
        if monto <= 0 or precio <= 0:
            continue

        cantidad = monto / precio
        if cantidad < STEP_MIN:
            minimo_requerido = calcular_monto_minimo(precio)
            print(f"⚠️ [{simbolo}] Monto insuficiente: qty={cantidad:.6f}, step={STEP_MIN} → se recomienda mínimo: {minimo_requerido} USDT")

if __name__ == "__main__":
    print("🔍 Validador de órdenes iniciado… (CTRL+C para salir)")
    while True:
        validar_ordenes()
        time.sleep(10)