# Ideas para mañana (15-nov-2026)

## 1. Activar "modo trabajo" con 2 palmadas o chasquido de dedos
- Detectar **2 palmadas** (o 2 chasquidos) seguidas en ~1 s para arrancar el modo trabajo.
- Idea técnica: escuchar el micrófono en segundo plano (`sounddevice`/`pyaudio`), buscar picos cortos de energía (transientes) y exigir 2 picos separados 0.2–0.8 s para evitar falsos positivos.
- Alternativa más robusta: modelo pequeño de clasificación de sonidos (p. ej. YAMNet / modelo "clap" ligero).
- Calibrar umbral según el ruido de la habitación.

## 2. Velocidad (PRIORIDAD)
Investigar y medir dónde se pierde tiempo (micrófono → transcripción → IA → voz).
- **Streaming en todo**: respuesta de la IA en streaming y TTS en streaming (empezar a hablar con la primera frase).
- **Transcripción más rápida**: `faster-whisper` local o STT en streaming.
- **Modelo más rápido** para respuestas cortas; el potente solo cuando haga falta.
- **ElevenLabs**: modelos de baja latencia (Flash / Turbo) y endpoint de streaming / websocket.
- Reutilizar conexiones, precargar modelos al iniciar, cachear frases frecuentes ("A sus órdenes, señor").
- Medir latencia por etapa con logs de tiempo antes y después.

## 3. Voz nueva
- Revisar la **Voice Library** de ElevenLabs para voces más parecidas a la que queremos.
- Ojo: las voces de personajes/actores reales con copyright normalmente no están disponibles o no se permiten clonar; buscar voces "estilo mayordomo británico/IA elegante" similares.
- Probar 3–4 voces y comparar.
