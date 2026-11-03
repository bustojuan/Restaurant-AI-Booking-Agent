# Contrato para el frontend

El detalle administrativo existente `GET /api/admin/observability/calls/{id}` añade `explanation`: solicitud minimizada, ofertas, hechos con referencias y guía de revisión. Los listados devuelven ese campo a null; no se añade otro endpoint. La proyección excluye contactos, restricciones personales y texto libre de proveedores; las lecturas no ejecutan agentes ni mutan negocio. Contratos OpenAPI regenerados. Detalles en [ADMIN_API.md](../ADMIN_API.md).

La telemetría normalizada para el futuro administrador se documenta en [ADMIN_API.md](../ADMIN_API.md) y [TRACE_SCHEMA.md](../TRACE_SCHEMA.md). Usa `/api/admin/observability`, con credencial independiente y acceso de lectura. La API de reservas y su WebSocket mantienen sus contratos; AI Control Center se abre en una ventana Electron independiente con IPC administrativo limitado y autenticación en Main. Ver [interfaz, endpoints y comandos](../../frontend/docs/control-center.md). JSON Schema: `contracts/observation-event.schema.json`.

Base: `http://127.0.0.1:8001/api`. REST protegido por `Authorization: Bearer <LOCAL_API_TOKEN>`, salvo salud. Fechas de reserva y horas locales en `Europe/Madrid`; timestamps de auditoría en ISO 8601 UTC. Las fechas pasadas se pueden conservar en borradores históricos; para iniciar se exige fecha futura y una hora local no ambigua ni inexistente por cambio horario.

## Endpoints disponibles

| Método y ruta (relativas a `/api`) | Respuesta / función |
|---|---|
| `GET /health` | Salud y modo `simulation` |
| `GET /restaurants` | Búsqueda combinada y paginada para mapa y listado |
| `GET /restaurants/categories` | Taxonomía normalizada, cocina y formato separados |
| `GET /restaurants/{id}` | Ficha, web, fotografías, atribuciones y favorito |
| `GET /favorites` | Favoritos paginados |
| `POST /favorites` | `{restaurant_id}`, idempotente, sin alterar la cola |
| `DELETE /favorites/{restaurant_id}` | Elimina favorito; idempotente, `204` |
| `GET /bookings` | Resúmenes paginados; filtro repetible `status` |
| `POST /bookings` | Crea borrador, configuración y selección inicial; `201` |
| `GET /bookings/{id}` | Configuración, versión, cola completa y `summary` |
| `PATCH /bookings/{id}` | Autosave parcial de configuración; requiere `If-Match` |
| `DELETE /bookings/{id}` | Elimina borrador; requiere `If-Match`, `204` |
| `POST /bookings/{id}/restaurants` | Inserta `{restaurant_id, position?}`; requiere `If-Match` |
| `PUT /bookings/{id}/restaurants/order` | Orden completo `{restaurant_ids}`; requiere `If-Match` |
| `DELETE /bookings/{id}/restaurants/{restaurant_id}` | Elimina y compacta posiciones; requiere `If-Match` |
| `POST /bookings/{id}/start` | `{scenario_id}`; requiere `If-Match` |
| `POST /bookings/{id}/cancel` | Cancela simulación; requiere `If-Match` |
| `POST /bookings/{id}/decisions` | `{offer_id, approve}`; requiere `If-Match` |
| `GET /bookings/{id}/offers` | Ofertas, evaluación y decisiones persistidas |
| `GET /bookings/{id}/events` | Eventos paginados mediante cursor |
| `GET /simulations/scenarios` | Escenarios de llamadas simuladas |
| `GET /workspace` | ID del borrador activo y versión independiente |
| `PUT /workspace` | `{active_draft_id: id o null}`; requiere su propio `If-Match` |
| `WS /events/ws` | Eventos globales o de un `booking_id`, con replay |

`GET /bookings/{id}` ya incluye la cola y el resultado; no hay rutas duplicadas `/status`, `/result`, `/restaurants/search` ni `/nearby`. El historial de intentos está en `summary.contacted_restaurants` y la confirmación en `summary.confirmation`.

## Búsqueda y persistencia independiente

El catálogo real y su actualización se describen en [restaurant-catalog.md](restaurant-catalog.md). El contrato añade `source_url`, `data_attribution`, `data_license_url` y `dietary_options`. Nuevos filtros en la ruta existente: `catalog=all|real|simulated|auto` (por defecto `all`), `cuisine_group=asian` y `dietary_options` repetible (AND). `auto` elige el catálogo real por región si existe, sin rellenar búsquedas vacías con simulados. Las opciones de menú son declaraciones de origen, no garantías de seguridad alimentaria. `/restaurants/categories` incluye ahora `dietary_options`. `q` busca también municipio y dirección.

Ejemplos (añadir cabecera de autorización):

```text
GET /restaurants?region=Madrid&cuisine_types=italian&establishment_types=pizzeria
GET /restaurants?region=Navarra&municipality=Pamplona&limit=20&offset=0
GET /restaurants?bbox=-3.72,40.40,-3.68,40.44
GET /restaurants?latitude=40.4168&longitude=-3.7038&radius_km=5&sort=distance
GET /restaurants?favorites_only=true&booking_id=<borrador>
GET /restaurants/categories
```

`bbox` usa **oeste,sur,este,norte**; coordenadas WGS84 en grados. Los campos de ficha se llaman `latitude` y `longitude`; GeoJSON utiliza `[longitude, latitude]`. `cuisine_types` y `establishment_types` son repetibles y se combinan por AND. Texto sin distinción de mayúsculas o acentos. Ordenaciones: `name`, `distance`, `rating`, `price`. Valores desconocidos de precio/valoración permanecen nulos, no satisfacen filtros y se ordenan al final. `limit` entre 1 y 100; `offset >= 0`.

`booking_id` es opcional y añade `selected_position` a los resultados visibles. No modifica nada. La selección completa debe leerse siempre desde el borrador: puede contener restaurantes que no aparezcan en el mapa o listado actuales. La búsqueda no guarda región, filtros ni vista, y no altera la cola, favoritos, configuración ni `workspace.active_draft_id`.

## Borradores, autosave y drag-and-drop

Crear un borrador vacío: `POST /bookings` con `{}`. También se admite `configuration` y `restaurant_ids` en el mismo alta. Su estado es `DRAFT` y su versión inicial es 1. Para restaurar sesión, leer `/workspace` y después `/bookings/{active_draft_id}`; alternativamente listar `/bookings?status=DRAFT`.

Seleccionar el borrador activo requiere `PUT /workspace`, usando **la versión de workspace**. Crear un borrador no sustituye automáticamente al activo. Arrancar, cancelar o eliminar el borrador activo limpia el puntero y aumenta la versión de workspace.

Las respuestas de reservas y workspace incluyen `version` y `ETag: "N"`. Cada edición envía `If-Match: "N"`. Configuración y cola comparten una versión por reserva; workspace tiene otra independiente. Autosave de ejemplo:

```http
PATCH /api/bookings/<id>
Authorization: Bearer <token>
If-Match: "1"
Content-Type: application/json

{"configuration":{"adults":4,"preferred_time":"21:00","notes":"Preferencia de terraza"}}
```

El patch mezcla únicamente los campos enviados; las listas de requisitos se reemplazan completas. Para borrar un valor opcional, enviar `null`. No se permite `null` en campos obligatorios. El esquema parcial enumera todos los campos admitidos en OpenAPI.

El cliente debe serializar los autosaves y conservar la nueva versión. `409 version_conflict` exige recargar y resolver los cambios, conservando las ediciones locales sin reenviarlas ciegamente. `428` indica que falta `If-Match`. No se sobrescribe una versión más reciente.

Para arrastrar un restaurante al índice 1:

```json
{"restaurant_id":"navarra-1","position":1}
```

Enviar a `POST /bookings/{id}/restaurants` con la versión actual. Índices **desde cero**, `0 <= position <= longitud`; omitir `position` añade al final. La inserción desplaza los siguientes restaurantes. Duplicados dan `409`; posición fuera de rango, `422`.

Para reordenar, enviar a `PUT /bookings/{id}/restaurants/order`:

```json
{"restaurant_ids":["navarra-1","madrid-2","madrid-1"]}
```

La lista debe contener exactamente los IDs actuales, una vez cada uno. El servidor valida la versión y actualiza todas las posiciones dentro de una transacción `BEGIN IMMEDIATE`. Las claves únicas impiden duplicar restaurante o posición dentro de una reserva. Los lectores ven un orden completo. Tras cada edición, la respuesta contiene la cola final y la versión nueva.

Solo se edita o elimina en `DRAFT`. En ejecución, espera de aprobación o estados finales, configuración y cola están bloqueadas. Favoritos y el explorador siguen siendo independientes.

## Ejecución y popover

`GET /bookings?status=RUNNING&status=WAITING_FOR_USER` devuelve ejecuciones activas; `status=DRAFT`, borradores. Para historial, combinar `CONFIRMED`, `EXHAUSTED`, `CANCELLED`, `FAILED`. Cada resumen contiene:

- `id`, `status`, `version`, fechas de creación, actualización, inicio y fin.
- `requested_date`, `preferred_time`, `timezone`, `party_size`.
- `current_restaurant` y `current_call_status`, nulos cuando no hay intento actual. Durante una aprobación se conserva el restaurante y la llamada consta completada.
- `contacted_restaurants`: intentos con restaurante, secuencia desde cero, estado, resultado, timestamps y duración.
- `pending_restaurants`, `total_restaurants`, `completed_attempts`.
- `pending_approvals`: ofertas concretas que permiten aprobar o rechazar.
- `confirmation`: solo existe después de la aceptación y confirmación explícita del proveedor. Incluye referencia y `simulated=true`.

Los pendientes son restaurantes nunca contactados; pueden quedar pendientes tras confirmación o cancelación. `completed_attempts` cuenta intentos que tienen `completed_at`, incluyendo errores o cancelación. Durante una aceptación tras aprobación, el intento vuelve a estar en curso hasta que el restaurante confirme.

Estados de reserva: `DRAFT`, `READY`, `RUNNING`, `WAITING_FOR_USER`, `CONFIRMED`, `EXHAUSTED`, `CANCELLED`, `FAILED`. `READY` queda reservado en el contrato; esta API valida y pasa directamente de `DRAFT` a `RUNNING`. Los estados y resultados de intento son enumeraciones de OpenAPI; un intento nuevo tiene `result=null` hasta que exista respuesta. No derivar estados ficticios en el frontend.

Iniciar: `POST /bookings/{id}/start` con `{"scenario_id":"priority-success"}`. Exige nombre, teléfono, fecha/hora futura y cola no vacía. Los reintentos del mismo inicio y escenario devuelven la ejecución existente, sin nuevas llamadas. Repetir cancelación tampoco duplica eventos.

Una oferta con condiciones económicas no autorizadas genera `WAITING_FOR_USER`; aprobarla solo autoriza el paso simulado de aceptación, sin procesar pagos. Las restricciones obligatorias incumplidas o sin evidencia no se convierten en confirmaciones. Un timeout durante la confirmación detiene toda la ejecución por incertidumbre.

## Eventos WebSocket y reconexión

Conectar a `ws://127.0.0.1:8001/api/events/ws?after_event_id=0`; añadir `booking_id=<id>` para una única reserva. Enviar como **primer frame**, en un máximo de 5 segundos:

```json
{"token":"<LOCAL_API_TOKEN>"}
```

El token nunca va en la URL. Se verifica el origen cuando existe. Cada frame posterior es un `EventOut`, exactamente igual al registro REST:

```text
event_id, event_type, schema_version=1, booking_id, timestamp,
payload.summary: BookingSummary
```

Tipos: `booking.created`, `booking.updated`, `restaurant.selected`, `booking.started`, `call.started`, `call.completed`, `alternative.proposed`, `user.approval_required`, `user.decision_received`, `booking.confirmed`, `booking.exhausted`, `booking.cancelled`, `booking.failed`.

La integración AI añade `agent.activity` al mismo flujo y cursor. Su payload mantiene `summary` y añade `activity` con agente, herramienta, fase, ejecución, ID de traza y latencia. Estos eventos no incrementan la versión editable del booking; los cambios de negocio sí lo hacen. No contienen razonamiento privado ni transcripciones inventadas.

El snapshot del resumen se persiste junto con el evento en la misma transacción que el cambio. La transmisión lee los eventos confirmados de SQLite aproximadamente cada 100 ms; no depende de mensajes en memoria. El flujo global permite actualizar el popover aunque otra ventana cree un borrador. Las modificaciones exclusivas de favoritos o workspace se recuperan por REST; no son eventos de ejecución.

Guardar el último `event_id` procesado y reconectar con `after_event_id` (exclusivo). Los IDs son crecientes globalmente y no se reutilizan; puede haber saltos al filtrar por reserva. REST: `GET /bookings/{id}/events?after_event_id=N&limit=100`, con `next_after_event_id` y `has_more`. Deduplicar por `event_id` y aplicar resúmenes solo si su versión no es anterior a la ya cargada por REST. En la primera conexión, cargar REST y reproducir desde 0 para cerrar la posible ventana entre snapshot y suscripción.

## Imágenes y web

`RestaurantOut` incluye `website_url`, `primary_image_url`, `images`, `additional_images` y `has_photo`. `images[0]` es la principal; `additional_images` contiene las restantes. Cada `ImageAsset` incluye fuente, página original, creador, atribución, licencia, URL de licencia y evidencia de derechos. El frontend debe mostrar la atribución junto a la imagen y conservar los enlaces correspondientes.

Sin datos verificados, la URL principal es `null`, los arrays están vacíos y `has_photo=false`. El frontend puede mostrar un marcador genérico de ausencia, sin presentarlo como una fotografía del establecimiento. Las imágenes no se infieren de OpenStreetMap ni se relacionan por nombres parecidos.

## OpenAPI y TypeScript

Swagger en `/docs`; OpenAPI en `/openapi.json`. Exportar desde `backend`:

```powershell
..\.venv\Scripts\python.exe scripts\export_contracts.py
```

Se generan `contracts/openapi.json` y `contracts/booking-event.schema.json`. `EventOut` también aparece en OpenAPI porque REST comparte el contrato. Para el futuro frontend, fuera de este backend:

```text
npx openapi-typescript backend/contracts/openapi.json -o api.generated.ts
```

Errores de aplicación: `{"error":{"code":"...","message":"..."}}`. `404` recurso ausente; `409` conflicto de versión, duplicado o estado; `422` validación; `428` falta versión; `503` base temporalmente no disponible. Las validaciones evitan devolver la entrada personal recibida. Rechazos de protocolo HTTP/host y cierres WebSocket siguen los formatos de transporte de Starlette/Uvicorn.

## Integración AI y voz

El endpoint de inicio existente admite `mode: simulation | ai_simulation | real_telephony`; por defecto conserva `simulation`. `real_telephony` requiere `call_authorization` tipada, habilitación y todos los controles documentados en `TELEPHONY_SETUP.md`. No hay un segundo endpoint que duplique el inicio de reservas.

| Método y ruta relativa a `/api` | Función |
|---|---|
| `GET /ai/capabilities` | Modos habilitados, modelos configurados y presencia de credenciales, sin secretos |
| `GET /bookings/{id}/ai` | Ejecución AI, prompts identificados, resumen y evaluación |
| `GET /bookings/{id}/ai/state` | Estado del grafo, próximos nodos e interrupciones; incluye el estado real de negocio |
| `GET /bookings/{id}/ai/traces?after_id=N&limit=50` | Actividad paginada de agentes y herramientas |
| `POST /bookings/{id}/ai/pause` | Pausa al final del intento actual; requiere versión |
| `POST /bookings/{id}/ai/resume` | Reanuda la coordinación; no aprueba ofertas, requiere versión |
| `DELETE /bookings/{id}/ai/data` | Elimina datos AI de una ejecución finalizada y reconciliada; requiere versión |
| `GET /ai/memories?scope=preference` | Memorias vigentes, con paginación |
| `POST /ai/memories/preferences` | Preferencia validada, consentimiento explícito y caducidad |
| `DELETE /ai/memories/{id}` | Elimina memoria |
| `GET /voice/bookings/{id}/calls` | IDs externos, transporte y reserva estimada de coste |
| `POST /voice/calls/{id}/reconcile` | Consulta del operador y atestación manual negativa; requiere versión |
| `WS /voice/sandbox/ws?booking_id=...` | Audio de prueba, opt-in, autenticación y consentimiento en primer frame |

Los esquemas de agentes se exportan también a `contracts/ai-contracts.schema.json`; el grafo, a `contracts/ai-graph.mmd`. El futuro frontend puede mostrar actividades y decisiones estructuradas del mismo sistema de eventos; no necesita reconstruir una máquina de estados de reservas.


## Release concurrency note

Booking and administrative WebSocket page reads run on worker threads. SQLite or
SQLAlchemy pool waits therefore do not block the ASGI event loop. Authentication,
event order, persisted cursors and REST/WebSocket schemas are unchanged. The
release includes a regression that stalls an observation read while asserting
that HTTP health remains responsive. See `tests/test_stream_concurrency.py`.

SQLite release defaults also use WAL with synchronous=FULL and short-lived
independent connections. BEGIN IMMEDIATE and version checks still serialize
mutations; reader snapshots no longer block writer commits. Supervisor storage
work runs on a worker and is awaited during shutdown before ownership is released.
