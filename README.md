# 🧠 SmartTrading Bot – Sistema de Alertas Cripto con Órdenes Interactivas

Este proyecto es un sistema completo de señales de trading en criptomonedas con confirmación interactiva por Telegram y ejecución en Binance (Spot). Incluye análisis técnico, IA integrada con Groq para validar oportunidades, gestión con trailing stop y dashboard visual de operaciones.

---

## ✅ Funcionalidades implementadas

- 📡 **Escaneo automático de mercado cada 5 minutos** usando indicadores técnicos reales (RSI, MACD, volumen, EMAs, patrones de velas).
- 🤖 **IA con Groq** (no `USE_FAKE_IA`) para validar señales y asignar índice de confiabilidad (0–100%).
- 📲 **Confirmación de órdenes desde Telegram** con botones (Sí/No) y monto editable.
- 💰 **Ejecución real de órdenes en Binance Spot** si el usuario confirma.
- 🧮 **Cálculo de cantidad basado en monto disponible** (USDT), redondeado según `stepSize`.
- 🔄 **Trailing stop automático** y cierre de operaciones según condiciones de TP o SL.
- 📉 **Filtro antiflood**: evita señales repetidas o redundantes.
- 📊 **Dashboard web** (`index.html`) con estado de operaciones confirmadas (entrada, SL, TP, precio actual, estado y PnL).
- 🧾 Configuración centralizada en `config.json`.

---

## ⚠️ Estado actual

El sistema está **funcionando parcialmente**:
- Se detectan y validan señales.
- Se envían correctamente a Telegram con botones y datos completos.
- Se ejecutan operaciones en Binance si se confirma por el usuario.
- El antiflood funciona.
- El dashboard carga correctamente y se actualiza.

Sin embargo, aún se están corrigiendo errores de consistencia en:
- Confirmación de órdenes desde Telegram cuando el JSON no está bien sincronizado.
- Cálculo correcto de la cantidad a comprar/vender en ciertos casos.
- Visualización o actualización puntual de PnL o confianza.

---

## 📂 Archivos principales

- `bot_integrado_final_CONTEXTUAL_histeresis.py`: lógica principal de escaneo, validación y envío de señales.
- `enviar_interactivo.py`: construcción y envío de mensajes con botones.
- `bot_interactivo.py`: escucha y procesa confirmaciones, ejecuta órdenes reales.
- `trailing_manager.py`: gestiona trailing stop y cierre de operaciones.
- `utils.py`: funciones auxiliares (precio actual, redondeo, filtros, IA, etc).
- `ordenes_pendientes.json`: órdenes pendientes de confirmación.
- `operaciones_trailing.json`: operaciones activas con seguimiento.
- `data.js + index.html`: dashboard visual en tiempo real.
- `.env`: claves de Binance y Telegram.

---

## ☑️ Requisitos para producción (Render/GitHub)

- Corregir todos los errores pendientes y probar el sistema en modo real.
- Validar que `bot_interactivo.py` maneje correctamente todas las órdenes.
- Verificar que `trailing_manager.py` cierre las órdenes correctamente.
- Confirmar que el dashboard refleje todos los cambios sin errores.

---

## 🔁 Continuar en otro chat

Usar el siguiente prompt maestro:
```
Estoy trabajando en un bot de alertas cripto con IA (Groq) que ejecuta órdenes reales en Binance Spot tras confirmación por Telegram. Ya tengo funciones operativas, pero quedan errores por corregir antes de subir a Render. No quiero perder nada del progreso ni repetir pasos. Ayudame a continuar desde donde dejé. Ya están cargados los archivos clave: `bot_integrado_final_CONTEXTUAL_histeresis.py`, `bot_interactivo.py`, `enviar_interactivo.py`, `trailing_manager.py`, `utils.py`, `config.json`, `ordenes_pendientes.json`, `operaciones_trailing.json`, `index.html`, `data.js`. La prioridad es que todo funcione sin errores.
```