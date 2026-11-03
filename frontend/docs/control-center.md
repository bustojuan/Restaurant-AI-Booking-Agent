# AI Control Center

El idioma de la interfaz es inglés (`en-GB`). Los registros originales, nombres y conversaciones conservan su idioma. Véase [English interface](english-ui.md).

Interfaz administrativa de escritorio integrada en el mismo proyecto Electron. Se abre en una ventana independiente; conserva el frontend de reservas, FastAPI, SQLite, LangGraph y la instrumentación existentes.

## Abrir

El acceso administrativo local ya puede prepararse sin mostrar el secreto:

```powershell
cd backend
..\.venv\Scripts\python.exe -m scripts.configure_admin
..\.venv\Scripts\python.exe -m app.main
```

`configure_admin` solo crea `ADMIN_API_TOKEN` cuando falta en `backend/.env`, usando un valor aleatorio independiente. No cambia un token existente. Si el backend estaba iniciado antes de configurarlo, reiniciarlo.

Desde otra terminal, en la raíz:

```powershell
.\scripts\start-control-center.ps1
```

Este comando compila y abre únicamente el administrador. No inicia otro backend. Para desarrollo con Vite: `-Development`; el puerto 5174 debe estar libre. Desde la aplicación de reservas, usar el botón **AI Control Center** o **Ctrl+Shift+A** (menú Desarrollo). La ventana se puede minimizar, maximizar, mover, redimensionar, cerrar y reabrir. Cerrar Electron no cancela ejecuciones del backend.

Desde el administrador, el botón **App de reservas** de la barra lateral (o **Ctrl+Shift+B**) abre la aplicación normal en otra ventana. Si ya existe, la restaura y trae al frente sin duplicarla. Ambas ventanas mantienen sus bridges separados; se puede cerrar cualquiera y reabrirla desde la otra. Al recuperar reservas se conserva el borrador activo persistido por el backend.

También se puede ejecutar desde `frontend`, con Node disponible:

```powershell
npm run dev:admin
# O, después de compilar:
npm run build
npm run start:admin
```

Si la terminal contiene `ELECTRON_RUN_AS_NODE`, los lanzadores administrativos lo eliminan del entorno hijo. El secreto se lee en Electron Main desde `backend/.env` o `ADMIN_API_TOKEN`. `BARIA_BACKEND_ENV` permite cambiar el archivo; `BARIA_BACKEND_URL` solo admite HTTP en localhost/127.0.0.1. El administrador no admite URLs arbitrarias ni navegación externa.

## Pantallas y comportamiento

El replay asocia cada entrada con una invocación concreta (span, grafo y thread). Solo esa entrada muestra un punto móvil; no se reutilizan entradas de visitas anteriores al Supervisor. Las rutas condicionales llevan etiquetas `Si: …`, y las líneas históricas permanecen estáticas. El encabezado del grafo identifica el número de invocación y el evento de entrada conservado; si falta, indica origen no registrado. No infiere actividad a partir de una flecha del grafo.

En el grafo de reservas, `negotiation` y `verification` se presentan como **Revisión de oferta** y **Revisión de confirmación**, después del contacto. Voice Session muestra los especialistas observados dentro del contacto, seleccionables para inspección. Esto es una proyección de spans/correlaciones conservadas; no crea nodos ni delegaciones históricos ausentes y no modifica el grafo ejecutable del backend.

La pestaña **Resumen del intento** contiene una explicación estructurada con referencias a solicitud minimizada, ofertas, evaluaciones, confirmación y eventos de negocio. Es una vista de los datos persistidos actuales, identificada como tal; no cambia al retroceder el replay. Cada enlace muestra su evidencia y los eventos disponibles también posicionan el cursor. Si hay purga, no reconstruye eventos ausentes.

La explicación distingue un intento completado sin aceptación registrada de una posible reserva sin confirmación verificable. El segundo muestra un procedimiento de revisión, sin ejecutar contactos ni reconciliación desde el administrador. La operación existente `POST /api/voice/calls/{id}/reconcile` sigue requiriendo token local, `If-Match`, credenciales y verificación del proveedor; registrar ausencia de reserva no reanuda la ejecución. En simulación se indica que el procedimiento real no debe llevar a contactar al restaurante.

La validación con sonido y telefonía sigue pendiente. Matriz preparada en [VOICE_ACCEPTANCE.md](../../backend/VOICE_ACCEPTANCE.md); el preflight no ejecuta esos escenarios.

- **Calls:** tabla central compacta, búsqueda literal por restaurante/llamada/reserva, estado, resultado, tipo, fechas Europe/Madrid, ordenación y páginas de 20. Booking view agrupa reservas con llamadas desplegables. Los filtros seleccionan reservas coincidentes y al desplegar se muestran todos sus intentos. Los intentos conservados sin captura siguen visibles; su grafo no se inventa. El tipo aparece como N/D si se ha perdido su procedencia.
- **Call Detail:** ficha del intento, resultado del backend, duración registrada, referencias técnicas y resumen guardado de la ejecución cuando existe. Ámbito de llamada con coordinación compartida, o ejecución completa de la reserva.
- **Agent Graph:** React Flow muestra las definiciones históricas conservadas, no el grafo actual proyectado sobre llamadas antiguas. Nodos coloreados por eventos `graph.node`; transiciones seleccionadas resaltadas por su propio evento. Zoom, pan, centrar y ampliar. La vista de agentes contrae rutas que atraviesan nodos técnicos conservando las aristas definidas; solo resalta una ruta contraída cuando todos sus tramos tienen transiciones registradas. “Ver nodos técnicos” muestra la definición completa. Las diferentes definiciones de booking/delegación se eligen en el selector del grafo.
- **Inspector:** invocaciones múltiples, Overview, I/O redactado, Tools, Timing y Errors. Modelo configurado y reportado se distinguen; no se expone razonamiento privado, textos libres ni secretos.
- **Conversation / Events:** eventos registrados de sesión, turnos, herramientas, delegaciones y negocio. La interfaz indica **“Transcripción no disponible para esta llamada”**, sin audio ni ondas simuladas.
- **Execution Timeline:** spans padre-hijo y eventos ordenados por timestamp/cursor. Incluye agentes, herramientas, nodos, transiciones y voz; filtros, zoom y scroll. Se puede ajustar ancho de paneles y alto de cronología mediante ratón o flechas en los separadores.
- **Replay:** play/pause, paso anterior/siguiente, 0.5×/1×/2×/4× y slider. Usa una instantánea REST paginada con `high_watermark` fijo. No llama a endpoints de ejecución, modelos, herramientas, decisiones ni telefonía. Los eventos futuros aparecen atenuados; solo cierres observados completan un span. Spans sin cierre quedan abiertos. “Seguir en directo” es una acción separada que actualiza la instantánea al recibir nuevos eventos.
- **Analytics:** cohorte por fechas/tipo/modelo/prompt, KPIs de intentos y reservas, evolución diaria, resultados, rendimiento de agentes, errores, herramientas, decisiones y consumo disponible. Empieza en simulación IA para evitar mezclarla con telefonía. “Todos los tipos” combina datos únicamente tras selección explícita.
- **Playground:** catálogo real de escenarios del backend, tamaño del grupo y flexibilidad, ejecución, evaluación, herramientas y acceso al detalle. Crea una reserva `ai_simulation` independiente con restaurantes marcados como simulados. No cambia el borrador activo, selección o favoritos. Exige extracción determinista; rechaza servicios de pago y parámetros de telefonía. El escenario `missing-evidence` configura una celiaquía ficticia con verificación obligatoria para ejercitar la política alimentaria existente. Los escenarios de aprobación permanecen esperando la decisión en la aplicación de reservas. Comparar prompts no está implementado y se indica.
- **Settings:** modelos configurados, versiones y hashes de prompts, proveedores, backend, instrumentación y retención. Solo lectura; no permite activar telefonía ni editar credenciales.

## Estructura

```text
src/admin/
  AdminApp.tsx      # shell, navegación, conexión y caché
  Calls.tsx         # TanStack Table, filtros y grupos
  CallDetail.tsx    # coordinación de paneles y cursor
  AgentGraph.tsx    # React Flow y definición histórica
  Inspector.tsx    # inspección contextual
  Timeline.tsx     # waterfall y reproducción visual
  Analytics.tsx    # Recharts y métricas persistidas
  Playground.tsx   # simulaciones existentes
  Settings.tsx     # configuración sin secretos
  api.ts           # cliente tipado, instantáneas paginadas
  replay.ts        # proyección pura de eventos
  types.ts         # tipos derivados de OpenAPI y bridge
  ui.tsx           # componentes compartidos; Tabs Radix
  admin.css        # identidad oscura uniforme
electron/main/
  admin-policy.ts  # operaciones IPC declaradas y validación Zod
  admin-events.ts  # WS autenticado, cursor y reconexión
```

## API consumida

Base: `/api/admin/observability`, mismo FastAPI en 8001.

| Método | Ruta                            | Uso                                                                                                                        |
| ------ | ------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| GET    | `/calls`                        | filtros `q`, `mode`, `status`, `result`, `date_from`, `date_to`, `model`, `prompt`; `sort`, `direction`, `limit`, `offset` |
| GET    | `/calls/{id}`                   | ficha de intento, referencias y procedencia                                                                                |
| GET    | `/bookings`                     | grupos paginados con todos sus intentos                                                                                    |
| GET    | `/executions/{id}`              | captura, versiones, cobertura y retención                                                                                  |
| GET    | `/events`                       | paginación existente por ejecución, cursor y límite fijo                                                                   |
| GET    | `/graphs/{version}`             | definición histórica inmutable                                                                                             |
| GET    | `/analytics`                    | agregados persistidos con filtros de cohorte                                                                               |
| GET    | `/settings`                     | configuración permitida, sin secretos                                                                                      |
| GET    | `/playground/scenarios`         | escenarios y disponibilidad                                                                                                |
| POST   | `/playground/runs`              | única escritura administrativa; simulación determinista                                                                    |
| GET    | `/playground/runs/{booking_id}` | evaluación, agentes y herramientas registrados                                                                             |
| WS     | `/events/ws`                    | primer frame autenticado desde Main; cursor global y reconexión                                                            |

El renderer solo puede invocar estas operaciones tipadas. Zod rechaza canales no declarados, URLs, IDs con traversal, límites incorrectos y campos adicionales. El token no se expone en preload, React, VITE, storage ni URLs WebSocket. Las peticiones administrativas solo se aceptan desde el main frame de la ventana administrativa. La ventana ordinaria no recibe el bridge administrativo; el administrador no recibe el bridge genérico de reservas. Se conservan sandbox, contextIsolation, CSP y webSecurity.

## Métricas y límites

Los intentos son la unidad de Calls; sandbox sin CallAttempt no se presenta como llamada. Analytics incluye reservas con al menos un intento coincidente. Las confirmaciones e intervenciones se calculan desde confirmaciones y decisiones de ofertas persistidas, incluso si se han purgado las trazas; una oferta aceptable no se presenta como confirmación. Un filtro de modelo/prompt selecciona ejecuciones con esos metadatos observados.

La duración media usa intentos con `duration_ms`. Los tiempos de agentes usan spans terminales conservados. La latencia de modelo usa spans de modelo completos. El consumo suma los spans canónicos de modelo/voz, no eventos de estado duplicados. No hay precio facturado por intento en el contrato actual: costes N/D, sin convertir presupuestos reservados en gastos. El resumen mostrado pertenece a la ejecución completa y no es una transcripción de llamada.

No hay backfill sintético para llamadas anteriores, audio almacenado, transcripciones completas, comparación de prompts, edición de configuración, autenticación multiusuario ni publicación web. La retención puede eliminar eventos manteniendo la ficha del intento. Los huecos y capturas purgadas se presentan explícitamente.

## Verificación

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
cd ../frontend
npm test
npm run build
npm run test:admin
```

Los tests de interfaz levantan SQLite temporal y un backend aislado en 18001. No usan la base de datos del usuario, claves de proveedores, llamadas externas ni audio real. Los datos mostrados en las capturas se generan mediante simulaciones identificadas como tales. Capturas de revisión: `docs/screenshots/control-center/`.
