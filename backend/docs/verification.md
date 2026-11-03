# Verificación de la implementación

## Observabilidad para el futuro administrador

La batería completa supera **147 pruebas**, con 13 avisos de deprecación de LangSmith/Python 3.14. Se añaden 12 casos que comprueban correlación, privacidad, replay sin ejecución, reinicio, cursores, aprobación, concurrencia, voz con transporte falso, retención, eliminación y fallos del almacenamiento. Se verificó migración `0004`/downgrade y correspondencia de metadatos en SQLite en disco. La evaluación offline mantiene **15/15**, cero solicitudes a modelos, cero llamadas telefónicas y cero confirmaciones falsas. Alcance y comandos en [ADMIN_TESTING.md](../ADMIN_TESTING.md).

## Catálogo real y diagnóstico de voz

La suite ampliada supera **129 pruebas**. Ruff comprueba y formatea 90 archivos. Se verifican migración 0003 y correspondencia de metadatos en SQLite en disco, normalización sin fotografías inferidas, caché/offline, conservación del snapshot ante fallo de Overpass, importación atómica con rollback, upsert idempotente, favoritos y orden conservados, protección de fichas activas, catálogo automático sin fallback ficticio ante búsquedas vacías, agrupación asiática y menú declarado. El preflight de voz no expone claves ni números; preparar un número propio crea una ficha nueva y no modifica las seleccionadas anteriormente.

Importación real completada desde Overpass: **9.217 Madrid + 787 Navarra = 10.004** fichas. Se creó copia SQLite antes de aplicar la migración. Se compararon reservas, orden y favoritos mediante huellas, y workspace frente a la copia: sin cambios. Consulta de comprobación: área central de Madrid con 2.685 resultados y página de 100, todos reales con atribución y sin fotos; búsqueda textual Pamplona con 44 resultados. La prueba de red fue la descarga manual del catálogo, separada de la suite automática.

Voz y telefonía siguen sin credenciales ni habilitación. El usuario ha decidido dejar pendiente su prueba real. Las pruebas locales cubren protocolo Live y controles de telefonía con transportes simulados; no prueban micrófono, voz generada, acceso al modelo ni llamadas externas. Diagnóstico: `python -m scripts.voice_preflight`.

## Ampliación AI y voz

Validación final en Windows y Python 3.14.3: **123 passed**, 13 avisos de deprecación de LangSmith, 68,34 segundos. La suite conserva las 69 pruebas originales y añade agentes, grafo persistente, pausas y aprobaciones tras reinicio, herramientas, evidencias, condiciones económicas, protocolo Live, integración de delegación y controles telefónicos.

El runner offline ha superado **15/15 casos**, sin solicitudes a modelos, sin llamadas telefónicas y sin prueba de audio real. Resultados individuales en [ai-evaluation-report.json](ai-evaluation-report.json). Documentación y límites en [AI_TESTING.md](../AI_TESTING.md).

También se han arrancado la API en `127.0.0.1:8001` y el gateway aislado en `127.0.0.1:8002`. La demostración HTTP con `--mode ai_simulation` confirmó `madrid-3` tras tres intentos y dejó `navarra-1` pendiente. Se verificaron por HTTP el resumen AI, checkpoint terminado, ocho versiones de prompts, OpenAPI y bloqueo de rutas de negocio/Swagger en el gateway. Ambos servidores de comprobación se detienen al finalizar.

No hay claves OpenAI ni credenciales Twilio configuradas: audio de micrófono, voz generada y llamadas reales no están comprobados. Telefonía y voz de pago permanecen desactivadas por defecto.

## Línea base anterior

Comprobado en Windows, Python 3.14.3, el 31 de octubre de 2026. Las pruebas emplean bases SQLite temporales en disco y no realizan llamadas a Internet.

| Verificación | Resultado |
|---|---|
| `python -m pytest -q` | **69 passed**, 22,45 segundos |
| `ruff check .` | Sin errores |
| `ruff format --check .` | 35 archivos conformes |
| `alembic check` | Sin nuevas operaciones de migración |
| Migración inicial, downgrade y nuevo upgrade | Verificados en pruebas |
| Arranque `python -m app.main` | Correcto en `127.0.0.1:8001` |
| Salud, filtro italiano/Madrid, categorías y OpenAPI por HTTP real | Correctos |
| `python scripts/demo_booking.py` por HTTP real | `CONFIRMED`, 3 intentos, `madrid-3` confirmado y `navarra-1` sin contactar |

La batería incluye:

- Inserción al principio, en medio y al final; reordenación y eliminación con posiciones persistidas y contiguas.
- Duplicados, órdenes incompletos, IDs ajenos y posiciones inválidas sin efectos parciales.
- Rollback completo ante fallo inyectado después de reescribir la cola.
- Peticiones realmente concurrentes con la misma versión: exactamente una se aplica; la otra recibe `409`.
- Persistencia de configuración, cola, favoritos y borrador activo tras búsquedas y reinicios.
- Autosave parcial, versiones ausentes/inválidas/obsoletas, borrado de borrador y limpieza del puntero activo.
- Bloqueo de configuración y cola durante ejecución, aprobación y tras confirmación.
- Recorrido secuencial por prioridades, agotamiento, confirmación explícita, falta de confirmación, errores y timeouts.
- Aprobación y rechazo, recuperación de aprobación tras reinicio y cancelación frente a respuestas tardías.
- Reconciliación de ejecución interrumpida sin contactar más restaurantes.
- Prevención de un segundo executor para la misma base SQLite.
- REST y WebSocket con el mismo snapshot, replay, flujo global, paginación de eventos y autenticación/origen.
- Identidad exacta del catálogo de fotos, ausencia de fotos, atribución/licencia obligatorias y revocación.
- Contratos OpenAPI, reglas de negociación, evidencias obligatorias y horas ambiguas/inexistentes por cambio horario.

Aviso de la batería: Starlette emite una deprecación sobre su integración actual de TestClient con `httpx`. No hay fallos de pruebas. Se mantiene `httpx` como cliente de pruebas y demostración, de acuerdo con el stack solicitado; no se ha ocultado el aviso.

La prueba no acredita restaurantes reales ni llamadas reales. El servidor de comprobación se detiene después de la verificación; se puede volver a iniciar con las instrucciones del README.
