# Arquitectura de voz

La observabilidad conserva sesión/intento/delegación/thread, tipos de comandos/eventos, metadatos provisionales de bloques por rol, offsets disponibles y llegada del primer audio. Registra la duración y uso recibidos sin conservar bytes ni transcripciones completas. Los checkpoints conversacionales del sandbox siguen siendo efímeros; su cronología minimizada puede consultarse posteriormente. Los relojes del proveedor permanecen separados de los offsets locales. Véase [TRACE_SCHEMA.md](TRACE_SCHEMA.md).

Se implementa el protocolo actual de **GPT-Live**, separado de Realtime. Se comprobó la documentación oficial antes de programar: [conexión WebSocket](https://developers.openai.com/api/docs/guides/voice-websockets), [delegación al cliente](https://developers.openai.com/api/docs/guides/live-delegation) y [gestión de sesiones](https://developers.openai.com/api/docs/guides/live-conversations). No se ha realizado una conexión de pago en esta sesión.

## Transporte y delegación

`LiveSession` conecta al endpoint Live, configura el modelo centralizado y espera `session.started`. Envía audio mediante `session.input_audio.append` y reproduce `session.output_audio.delta`. No utiliza nombres de eventos de Realtime para fingir compatibilidad.

La voz y las tareas delegadas se ejecutan en tareas asíncronas independientes. `session.delegation.created` aporta un ID y metadatos, no el texto de la tarea. La aplicación mantiene una ventana transitoria de las transcripciones del proveedor, con roles y marca provisional; nunca inventa fragmentos ausentes. El servicio prepara una solicitud a partir de esa ventana y del estado vigente del backend.

Un grafo corto persistente resuelve la delegación: `route → requirements / negotiate / verify / decline / clarify → END`. Solo se invoca al delegar; el audio no pasa por LangGraph. El resultado vuelve con el mismo ID mediante un append conciso de commentary o thinking. Los resultados de una revisión obsoleta se descartan.

La apertura solicita identificación como asistente de IA. El modelo recibe instrucciones para respetar negativas, preguntar sin insistir y no comprometer condiciones sin autorización. La aceptación se comunica a la voz únicamente después de que el motor la haya validado y persistido. Una afirmación de confirmación no solicitada se trata como un caso de reconciliación.

## Audio y cierres

Sandbox: PCM16 mono a 24 kHz. Telefonía: G.711 μ-law mono a 8 kHz, compatible con Media Streams, sin conversión innecesaria. Los bytes se transportan en orden y sin cabeceras WAV.

Hay colas acotadas, reproducción en fragmentos de 20 ms y control local de limpieza del audio encolado cuando aparece una interrupción. GPT-Live mantiene su propia conversación full duplex; no se le envían comandos `response.cancel` ni truncados de Realtime. La limpieza local basada en fragmentos de transcripción es una heurística pendiente de validación con audio real, ruido y dispositivos.

El cierre solicita `session.close` y espera `session.closed`; si falta, no se inventa uso final. Un cierre de transporte no prueba que el interlocutor oyera íntegramente un mensaje. La entrega de la presentación de IA, el turn-taking y la latencia percibida deben comprobarse escuchando la prueba real antes de usarlo con personas externas.

## Probar el sandbox sin llamar por teléfono

Antes de empezar, `python -m scripts.voice_preflight` informa de configuración ausente sin capturar audio ni abrir conexiones. Un informe preparado no demuestra acceso al modelo ni calidad de audio.

1. Instalar el extra de audio y arrancar la API local:

```powershell
..\.venv\Scripts\python.exe -m pip install -e ".[dev,audio]"
```

2. Configurar `OPENAI_API_KEY` y `VOICE_SANDBOX_ENABLED=true` en `.env`; dejar `REAL_TELEPHONY_ENABLED=false`. Reiniciar el servidor.
3. Crear un borrador con una configuración de prueba y obtener su ID.
4. Usar auriculares y ejecutar:

```powershell
..\.venv\Scripts\python.exe scripts\voice_sandbox.py --booking-id <id> --allow-api-costs --consent-audio-processing
```

El script usa micrófono y altavoz mediante `sounddevice`; no crea una interfaz visual. La autenticación y el consentimiento se envían en el primer frame del WebSocket local. La clave OpenAI permanece en el servidor. Ctrl+C solicita un cierre ordenado. El sandbox no cambia el borrador ni realiza reservas.

La ruta es `/api/voice/sandbox/ws?booking_id=<id>`. Está bloqueada por defecto y exige token local, habilitación, clave y aceptación explícita del coste y del tratamiento de audio. Los checkpoints de conversación de sandbox se eliminan al cerrar. Si el proceso cae, pueden quedar datos estructurados de delegación hasta su limpieza; no hay audio ni conversaciones completas persistidas.

Estado comprobado: transporte y delegación se prueban con eventos y bytes sintéticos, incluyendo ejecución real del grafo de backend. Micrófono, síntesis del modelo, calidad de voz, disponibilidad de cuenta y telefonía externa **no se han probado**, por ausencia de credenciales.
