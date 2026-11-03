# Lectura de observabilidad

`GET /calls/{id}` incluye `explanation` con `requested`, `offers`, `facts`, `review`, estado/versión de reserva e indicador de simulación. Cada hecho contiene referencias tipadas a solicitud, oferta, evaluación, confirmación, resultado o cursor de evento conservado. No publica contactos, valores alimentarios ni entradas/salidas libres. La explicación describe registros actuales, no una reconstrucción de conversaciones ni una evaluación ejecutada de nuevo. `explanation` es null en listados para evitar consultas de detalle por cada fila.

`review.category` distingue `continue` (intento completado sin aceptación registrada y transporte concluido o simulado), `review_required` (posible reserva sin confirmar), `unknown` (captura insuficiente), `reconciled` (atestación del operador persistida) y `none`. Los metadatos ausentes no se convierten en permiso para continuar. La guía no ejecuta la reconciliación: el endpoint local existente exige token local, versión y consulta al proveedor. Una atestación no reanuda una reserva detenida. En simulación la guía indica expresamente no contactar al restaurante por el resultado de prueba.

Base: `http://127.0.0.1:8001/api/admin/observability`. Comparte FastAPI y SQLite con la aplicación. Las consultas históricas son de lectura; replay nunca lanza agentes. La única escritura administrativa es `POST /playground/runs`, para simulación determinista aislada.

Configurar en `backend/.env` un `ADMIN_API_TOKEN` aleatorio de al menos 24 caracteres, diferente de `LOCAL_API_TOKEN`, y reiniciar la API. Sin configuración, REST responde 503 y WebSocket rechaza el acceso. La instrumentación persiste independientemente de que la lectura administrativa esté habilitada. No guardar esta credencial en el renderer ni enviarla por query string.

REST utiliza `Authorization: Bearer <ADMIN_API_TOKEN>`. El token ordinario de la aplicación no autoriza estas rutas. Se mantiene la API anterior de actividad/reservas y no se publica el gateway de telefonía como API administrativa.

| Método y ruta relativa | Respuesta |
|---|---|
| `GET /executions` | Capturas paginadas; `booking_id`, `mode`, `limit` 1..100, `offset` |
| `GET /executions/{execution_id}` | Correlaciones, versiones, tiempos, estado actual de la reserva y cobertura; spans sin cierre, errores de escritura conocidos |
| `GET /events` | Eventos con `execution_id`, `call_attempt_id`, `after_event_id`, `until_event_id`, `limit` 1..200 |
| `GET /graphs/{graph_version}` | Definición inmutable de un grafo conservado |
| `WS /events/ws` | Stream global o filtrado por `execution_id`, con replay desde `after_event_id` |

Modos: `simulation`, `ai_simulation`, `real_telephony`, `voice_sandbox`. `/executions` no fabrica capturas anteriores: puede estar vacío y un detalle ausente devuelve 404. `/calls` sí muestra intentos conservados sin captura, con cobertura `unavailable`. Los intentos y trazas anteriores siguen disponibles en sus endpoints existentes, con sus límites históricos.

Cada página de eventos ofrece `items`, `has_more`, `next_after_event_id` y `high_watermark`. Para una captura fija, usar el `high_watermark` inicial como `until_event_id` en las siguientes páginas. Para seguir eventos nuevos, continuar con el cursor sin ese límite.

El WebSocket valida origen cuando se envía. Después de conectar se dispone de cinco segundos para el primer mensaje:

```json
{"token": "<ADMIN_API_TOKEN>"}
```

Se envía un `ObservationEventOut` por frame. El cursor queda en SQLite y puede recuperarse por REST o al reconectar. No se incluyen resúmenes con datos personales en estos frames. Una autenticación inválida cierra con 1008. Cada cliente desduplica por `event_id`/`id` y conserva el último cursor procesado.

El token es una frontera local de desarrollador, no un sistema multiusuario con roles, cuentas o auditoría de inicios de sesión. La ventana independiente AI Control Center dispone de un bridge tipado y limitado; el renderer ordinario no recibe acceso administrativo. Ver [interfaz, rutas y comandos](../frontend/docs/control-center.md).

## Proyecciones del Control Center

Se añaden `GET /calls`, `/calls/{id}`, `/bookings`, `/analytics`, `/settings`, `/playground/scenarios`, `/playground/runs/{booking_id}` y `POST /playground/runs`. Reutilizan las tablas y servicios existentes sin migraciones adicionales. [Contratos y filtros detallados](../frontend/docs/control-center.md#api-consumida).
