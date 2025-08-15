import json
import os
import time
import datetime
from binance.client import Client
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
client = Client(api_key, api_secret)

RUTA_OPERACIONES = "Dashboard/data.js"

def leer_operaciones():
    with open(RUTA_OPERACIONES, "r", encoding="utf-8") as f:
        raw = f.read()
    raw_json = raw.split("const operaciones =")[1].strip().rstrip(";")
    return json.loads(raw_json)

def guardar_operaciones(operaciones):
    contenido = "const operaciones = " + json.dumps(operaciones, indent=2) + ";"
    with open(RUTA_OPERACIONES, "w", encoding="utf-8") as f:
        f.write(contenido)

def obtener_precio_actual(simbolo):
    ticker = client.get_symbol_ticker(symbol=simbolo)
    return float(ticker["price"])

def trailing_manager():
    operaciones = leer_operaciones()
    actualizadas = []
    for op in operaciones:
        if op["estado"] != "Confirmada":
            actualizadas.append(op)
            continue

        simbolo = op["simbolo"]
        entrada = float(op["precio_entrada"])
        cantidad = float(op.get("cantidad", 0))
        trailing_pct = float(op.get("trailing_pct", 0.03))
        sl = float(op.get("sl", 0))
        tp = float(op.get("tp", 0))
        max_price = float(op.get("max_price", entrada))
        trailing_stop = float(op.get("trailing_stop", entrada * (1 - trailing_pct)))

        precio_actual = obtener_precio_actual(simbolo)
        max_price = max(max_price, precio_actual)
        nuevo_trailing = max_price * (1 - trailing_pct)

        print(f"⏳ Seguimiento {simbolo}: precio={precio_actual:.4f} max={max_price:.4f} stop={nuevo_trailing:.4f}")

        op["max_price"] = max_price
        op["trailing_stop"] = nuevo_trailing
        op["precio_actual"] = precio_actual

        if not cantidad or float(cantidad) <= 0:
            print(f"❌ No se puede vender {simbolo}: cantidad inválida ({cantidad})")
            actualizadas.append(op)
            continue

        activar_venta = False
        motivo = ""

        if precio_actual <= sl:
            activar_venta = True
            motivo = "SL"
        elif precio_actual <= nuevo_trailing:
            activar_venta = True
            motivo = "Trailing"

        if activar_venta:
            try:
                orden = client.order_market_sell(symbol=simbolo, quantity=cantidad)
                precio_venta = float(orden["fills"][0]["price"])
                op["estado"] = "Cerrada"
                op["venta"] = precio_venta
                op["estado"] = "Cerrada"
                op["motivo_cierre"] = motivo
                op["pyl_usdt"] = round((precio_venta - entrada) * cantidad, 4)
                op["pyl_pct"] = round(((precio_venta / entrada) - 1) * 100, 2)
                print(f"✅ Vendido {simbolo} a {precio_venta} — motivo: {motivo}")
            except Exception as e:
                print(f"❌ Error vendiendo {simbolo}: {str(e)}")
        actualizadas.append(op)

    guardar_operaciones(actualizadas)

if __name__ == "__main__":
    while True:
        trailing_manager()
        time.sleep(15)
