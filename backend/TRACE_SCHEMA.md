# Esquema de eventos, versión 1

Contrato exportado: `contracts/observation-event.schema.json`. OpenAPI incluye `ObservationEventOut` y `ObservationPage`. El evento es independiente de React, Electron y del futuro estado visual del panel.

El sobre contiene cursor/UUID, correlaciones, tipo y fase, tiempos UTC/offsets, duración medida, versiones de grafo/modelo/prompt y `data`. Los IDs desconocidos son nulos. Los consumidores deben tolerar nuevos tipos y usar el ID para ordenar/desduplicar; la fecha del proveedor no sustituye al cursor de recepción.

| Tipo | Hecho registrado |
|---|---|
| `agent` | Inicio y final de una invocación de agente existente |
| `tool` | Herramienta autorizada y validada, proyecciones de entrada/salida; `cached=true` cuando devuelve una operación idempotente ya resuelta |
| `model` | Solicitud efectiva al extractor Responses, modelo configurado/reportado y uso recibido |
| `graph.node` | Invocación del nodo identificado por `node`; incluye pasos de coordinación que no son agentes |
| `graph.transition` | Arista seleccionada, con origen, destino y carácter condicional |
| `graph.invocation`, `graph.checkpoint` | Invocación del grafo y referencia al checkpoint observado al volver; número de nodos pendientes |
| `delegation` | Inicio y fin del trabajo delegado, correlacionado con el ID de delegación y thread propios |
| `voice.session` | Sesión de voz y su duración/uso disponibles; no acredita que una reserva se haya confirmado |
| `voice.provider`, `voice.command` | Tipos de evento/comando observados; se omite su contenido textual |
| `voice.audio` | Primer audio entrante enviado y primer audio saliente recibido; sin bytes de audio |
| `voice.turn` | Bloque de transcripción observado por rol, ID local, caracteres y timestamps disponibles; contenido omitido, provisionalidad explícita |
| `voice.delegation` | Delegación recibida una vez después de desduplicarla |
| `transport.dial`, `voice.transport` | Preparación, invocación de marcado, respuesta, vinculación autenticada, callbacks, incertidumbre y cierre observados |
| `agent.decision` | Evaluación/verificación estructurada producida por un agente, sin respuesta hablada |
| `backend.*` | Referencia a un evento o acción comprometidos del motor, decisiones y confirmaciones |
| `telemetry.gap` | Número conocido de escrituras fallidas al recuperar el almacenamiento |
| `legacy.activity`, `model.usage` | Actividades puntuales compatibles con emisores anteriores; no se convierten en invocaciones completas inventadas |

Los spans usan `started` y `completed/failed/interrupted/cancelled`. Interrumpir LangGraph es control de flujo, no un fallo del agente. No se genera un final para un span cuyo cierre no se observó. Otras fases describen hechos puntuales: `selected`, `committed`, `observed`, `received`, `prepared`, `callback`, etc.

`ModelUsage` acepta contadores numéricos explícitos: entrada, salida, total, audio/caché y duración del proveedor. Lo ausente queda ausente/nulo; no se calcula coste facturado a partir de tarifas supuestas. La reserva de gasto de telefonía es `reserved_cost_eur`, distinta del gasto real. Para agregar uso se emplean los finales de `model` y `voice.session`; los mensajes de cierre de proveedor no duplican ese uso en el stream normalizado.

Los bloques `voice.turn` conservan snapshots de metadatos, no del texto: el conteo posterior sustituye al anterior para el mismo `turn_id`. El cambio de rol no acredita una transcripción final del proveedor. El primer audio recibido mide llegada al servidor, no que el interlocutor lo haya oído. No se estiman TTFT, sentimiento, forma de onda ni duración de habla ausentes.
