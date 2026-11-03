# Convenciones del repositorio

- Backend Python en `backend/`, FastAPI + Pydantic v2 + SQLAlchemy 2 + SQLite + Alembic.
- Ejecutar herramientas desde `backend` con `../.venv/Scripts/python.exe` en Windows.
- Separar API, contratos, servicios, repositorios y proveedores. Las rutas no contienen reglas de negociación.
- Modos: simulación clásica, simulación con LangGraph, voz sandbox y telefonía real. Voz de pago y telefonía están desactivadas por defecto. Nunca realizar llamadas externas como parte de tests automáticos.
- BookingExecutionService es el único propietario de las transiciones de reserva. LangGraph coordina mediante herramientas acotadas; los agentes no pueden escribir confirmaciones por su cuenta.
- Los checkpoints usan SQLite y durabilidad síncrona. Las interrupciones se reanudan leyendo la decisión persistida del backend. Un timeout externo ambiguo nunca permite una rellamada automática.
- Probar telefonía únicamente con números propios explícitamente autorizados y todos los límites activos. Mantener el gateway público separado de la API local.
- Frontend de escritorio en `frontend/`: Electron, React y TypeScript. La solicitud de frontend autoriza esta capa; preservar la lógica existente de reservas, agentes y telefonía.
- El renderer solo accede a FastAPI mediante el preload tipado. Tokens y credenciales permanecen en el proceso principal/backend.
- Las escrituras de reservas y de la cola pasan por transacción `BEGIN IMMEDIATE` y comprobación de versión.
- La configuración y la cola solo son editables en `DRAFT`. Búsquedas nunca mutan selección ni favoritos.
- Nunca inferir una confirmación a partir de una oferta aceptable.
- No inventar fotos, teléfonos, precios ni valoraciones. Mantener identidad, licencia y atribución de imágenes.
- Cambios de modelos persistidos requieren migración Alembic y pruebas con SQLite en disco.
- Actualizar `docs/frontend-api.md` y regenerar `contracts/` al modificar contratos.
- Validar con `python -m pytest -q`, `ruff check .`, `ruff format --check .`.
- No registrar tokens, teléfonos, configuración personal ni datos alimentarios.
- No persistir audio ni conversaciones completas. Las citas breves de evidencia requieren procedencia real y retención limitada. LangSmith está desactivado por defecto.
- Instrumentar nuevas operaciones mediante `app/observability/`: spans correlacionados y proyecciones permitidas, sin entradas/salidas libres. Distinguir nodos, agentes, herramientas, modelos y eventos de negocio. No reconstruir hechos históricos ausentes ni reejecutar trabajo para replay.
- Mantener cursores de observabilidad SQLite AUTOINCREMENT y retención con marcador de purga. Las consultas `/api/admin/observability` son de lectura y requieren token administrativo independiente; no exponerlo en el renderer ni en URLs.
- Actualizar los seis documentos AI/voz, prompts versionados y evaluaciones al cambiar la orquestación. Distinguir siempre pruebas de texto, protocolo, audio real y llamadas reales.


- AI Control Center usa ventana y bridge administrativos independientes. Mantener lecturas de replay separadas de `POST /playground/runs`; esta escritura solo admite simulaciones deterministas con restaurantes de prueba y no modifica workspace/favoritos. Nunca habilitar modelos de pago o llamadas desde Playground.
