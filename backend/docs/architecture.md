# Arquitectura e interfaces de extensión

La API llama a servicios de negocio; los servicios consultan repositorios y modifican entidades dentro de transacciones SQLite. Los esquemas Pydantic constituyen el contrato REST y de eventos. Las prioridades pertenecen a `BookingRestaurant`, no al restaurante ni a la búsqueda. Favoritos y workspace tienen tablas propias.

`Database.transaction(write=True)` obtiene `BEGIN IMMEDIATE` antes de leer la versión. Esto serializa escritores sin hacer llamadas de red dentro de una transacción. La versión compara la intención del cliente con el estado persistido; las restricciones SQL protegen duplicados y posiciones. Referencias técnicas: [aislamiento de SQLite](https://sqlite.org/isolation.html) y [control de transacciones SQLAlchemy/SQLite](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#transactions-with-sqlite-and-the-sqlite3-driver).

Un supervisor local descubre reservas `RUNNING`, y mantiene una tarea por reserva. Los intentos se guardan antes de invocar `CallProvider`. Hay unicidad por reserva/restaurante y confirmación por reserva. Un bloqueo de fichero limita el executor a un proceso por base; no usar múltiples workers. El arranque reconcilia ejecuciones interrumpidas a `FAILED` sin reintentar llamadas inciertas. Las aprobaciones conservadas se reanudan tras una decisión explícita. Nunca se confirma solo porque una política declare la oferta aceptable.

## Restaurantes e imágenes

`RestaurantProvider.records()` devuelve contratos normalizados, actualmente con `MockRestaurantProvider`. Para una futura importación real: validar coordenadas, URL web y metadatos; mantener `source` + `external_id` estables, no inventar datos ausentes y aplicar atribuciones y reglas de almacenamiento del proveedor. El catálogo local actual es pequeño; texto, categorías y radio se filtran en Python después de filtros SQL. Antes de importar volúmenes grandes, llevar estas consultas al proveedor o a índices geográficos sin alterar el contrato público.

`RestaurantImageProvider.images_for(RestaurantIdentity)` funciona de forma independiente. Proveedores disponibles: `NoImageProvider` (por defecto) y `VerifiedCatalogImageProvider` (manifiesto JSON local opcional). El proveedor solo admite correspondencia exacta por fuente e ID externo. No descarga, replica ni busca fotografías por nombre o cercanía. No depende de que OSM contenga imágenes.

Formato de `IMAGE_CATALOG_PATH`: un array de entradas con `source`, `external_id` e `images`. Cada imagen debe cumplir `ImageAsset` (consultable en OpenAPI/JSON Schema). Lista vacía significa ausencia; el orden elige la principal. No se incluye un manifiesto con fotografías de ejemplo para evitar atribuir imágenes ajenas a los restaurantes simulados.

Licencias admitidas por el contrato: `CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0` o `OWNER_PERMISSION`. Se exigen creador, atribución, página original, URL de licencia, evidencia de derechos y `rights_verified=true`. Esta marca es una declaración del operador, no una verificación automática. Antes de importar, el operador debe comprobar que la foto corresponde al restaurante y que el uso concreto está autorizado. Para permisos propios se exige evidencia documentada; no basta con que la imagen sea pública.

En este backend solo se conservan las URLs y los metadatos de derechos; no los binarios. El manifiesto se aplica al arrancar y elimina imágenes de entradas revocadas. No usar fuentes cuyas condiciones impidan persistir esos metadatos. Un futuro proveedor con URLs temporales, expiración, prohibición de almacenamiento o requisitos de redistribución deberá implementar su propio ciclo de validez antes de integrarse. La UI deberá cumplir atribución y condiciones de la licencia; el backend no otorga derechos sobre imágenes.

## Frontend y mapa

Electron/React consume REST y WebSocket con el token local, custodiado por el proceso principal. MapLibre recibe coordenadas y fichas de la misma búsqueda que la vista listado. Edificios 3D, tiles, estilos, rotación y perspectiva pertenecen al frontend. No hay ningún componente visual en el repositorio. La guía completa está en [frontend-api.md](frontend-api.md).

## Telefonía y agentes futuros

`CallProvider.contact()` produce una respuesta estructurada; `confirm()` exige una aceptación separada y devuelve evidencia explícita. El `operation_id` es estable por intento para futura idempotencia. `MockCallProvider` solo genera datos simulados. La interfaz actual representa únicamente evidencias simuladas; un proveedor real requerirá ampliar el contrato, gestionar incertidumbre, cancelación y reconciliación, y conservar evidencia autorizada antes de habilitar llamadas.

`NegotiationPolicyService.evaluate()` comprueba fecha, hora, personas, mesa, presupuesto y evidencias obligatorias. Los requisitos extensibles utilizan claves y valores; una futura llamada debe verificar explícitamente el valor solicitado y solo entonces marcar su evidencia como cierta. Accesibilidad, tronas, carrito y necesidades alimentarias se validan explícitamente cuando son obligatorios. Las preferencias negociables no se convierten silenciosamente en condiciones obligatorias.

La capa AI ya envuelve estos servicios mediante capacidades acotadas. LangGraph y su checkpointer SQLite están instalados, junto a LangChain Core, OpenAI y Twilio. La selección del siguiente restaurante y el guardado de resultados permanecen en `BookingExecutionService`; los agentes no escriben confirmaciones directamente ni saltan versiones o políticas. El modo simulado anterior se conserva. Arquitectura, activación y estado real de pruebas en [AI_ARCHITECTURE.md](../AI_ARCHITECTURE.md), [VOICE_ARCHITECTURE.md](../VOICE_ARCHITECTURE.md) y [TELEPHONY_SETUP.md](../TELEPHONY_SETUP.md).
