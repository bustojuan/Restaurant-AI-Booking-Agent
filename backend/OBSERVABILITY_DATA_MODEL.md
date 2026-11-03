# Modelo de observabilidad

## Tablas añadidas por `0004`

| Tabla | Función |
|---|---|
| `observed_executions` | Índice de captura para reserva clásica, AI, telefonía o sandbox; referencia opcional a `AIExecution`, versión de grafo, referencias de prompts, modelos configurados y límites temporales de captura |
| `observation_graph_versions` | Definición inmutable obtenida del grafo compilado: nodos, aristas, condiciones, versiones de librerías y huella de implementación |
| `observation_events` | Hechos ordenados: spans, transiciones, herramientas, decisiones, checkpoints y metadatos de voz/transporte |

El ID de captura coincide con `AIExecution.id` en los modos AI, con `BookingRequest.id` en la simulación clásica y con el UUID local de sesión en sandbox. `booking_id` siempre referencia la reserva. Estas reglas no crean una ejecución LangGraph para modos que no la tienen.

## Correlación

| Campo | Procedencia |
|---|---|
| `id` / `event_id` | Cursor entero global SQLite AUTOINCREMENT y UUID de evento; no se reutilizan cursores al borrar filas |
| `execution_id`, `booking_id` | Captura y reserva existentes |
| `call_attempt_id` | Intento real de `call_attempts`, cuando ya existe |
| `call_session_id` | `VoiceCallSession.id`, o identidad local del sandbox cuando está disponible |
| `external_call_id`, `external_session_id` | Identificadores observados de Twilio y GPT-Live; nunca teléfonos |
| `graph_thread_id`, `checkpoint_id` | Thread y checkpoint reales; las delegaciones tienen su propio thread `voice:<scope>:<delegation_id>` |
| `graph_version` | Hash de la definición conservada del grafo correspondiente a ese evento |
| `span_id`, `parent_span_id` | Invocación y padre conocido; cada nueva invocación obtiene otro UUID |
| `agent_run_id`, `tool_call_id`, `delegation_id` | Invocación de agente, invocación de herramienta y delegación del proveedor |
| `node`, `agent`, `tool` | Nodo ejecutado, rol y herramienta observados; son conceptos distintos |

La sesión del stream Twilio se conserva como `data.provider_stream_id` en el evento de vinculación autenticada. Antes de crear un intento no se inventa su ID: planning/research pueden quedar asociados solo a reserva y ejecución. La versión principal del grafo de la captura se conserva; los eventos identifican también el grafo de cada delegación.

## Tiempos y resultados

`occurred_at` y `received_at` son UTC del servidor. Los offsets de ejecución e intento usan sus orígenes locales persistidos. `elapsed_ms` se mide con reloj monotónico dentro del proceso. Los offsets de voz entregados por el proveedor se conservan aparte; no se asume sincronización entre relojes.

Los estados y resultados del negocio se toman de sus filas y eventos comprometidos, con referencias a oferta, decisión y confirmación. No se acepta una reserva a partir de una traza. Una transición de grafo registrada como `selected` indica la ruta seleccionada; la entrada efectiva se comprueba con el siguiente `graph.node.started`.

`ended_at` referencia el cierre de negocio en reservas y la salida del handler en sandbox. Las duraciones de procesamiento AI y los pasos posteriores al cierre de negocio se obtienen de sus spans; no se recorta la cronología al instante de confirmación. Los eventos generales de reserva no se atribuyen automáticamente al último intento: el ID se enlaza en hechos de llamada, decisión, confirmación o fallo que disponen de ese contexto.

## Contenido y retención

Los datos de eventos pasan por una lista de campos Pydantic permitidos. Las entradas y salidas de herramientas son proyecciones: presencia, conteos, estados, evaluación e IDs autorizados. No incluyen nombres, teléfonos, fechas/personas solicitadas, necesidades alimentarias, ofertas completas, mensajes, prompts dinámicos, audio ni transcripciones. Los errores contienen clase/código y omiten el mensaje original.

Se guardan versión y SHA-256 del prompt base. Las copias de prompts del sistema ya existentes en `AIExecution` mantienen su política previa; el contexto personalizado no se copia a observabilidad. `configured_models` indica configuración, no consumo ni versión resuelta. `reported_model` solo aparece si el proveedor lo entrega.

Se utiliza `AI_RETENTION_DAYS` (30 por defecto). El mantenimiento periódico elimina eventos vencidos de capturas finalizadas y sandbox antiguos incluso si un cierre no quedó registrado. Conserva un marcador `events_pruned_at` para explicar la ausencia de datos. Sesiones reales ACTIVE/DIALING/UNCERTAIN protegen sus eventos hasta reconciliarse. El borrado AI existente elimina la captura AI y sus eventos por cascada; borrar una reserva elimina sus capturas. Las definiciones de grafo compartidas no contienen datos de conversación.

`coverage=recorded` significa que existen eventos, no que el histórico sea completo. `open_span_ids`, `dropped_events`, fechas de instrumentación y `coverage=pruned/empty/degraded` permiten señalar información incompleta. No se rellenan ejecuciones antiguas con eventos sintéticos.
