# Catálogo local de restaurantes reales

**Public release:** only clearly labelled mock restaurant fixtures are seeded by
default. The developer's cached catalog/database is not distributed. Use the
manual import below to obtain your own current public-source catalog. Historical
import counts in this document describe a development snapshot, not bundled
records or guaranteed current coverage.

La primera importación contiene **9.217 fichas de Madrid y 787 de Navarra** procedentes de OpenStreetMap. Son establecimientos etiquetados como `restaurant` o `fast_food`, con nombre y coordenadas. No constituye un censo completo ni acredita apertura, disponibilidad o aceptación de reservas. Los datos ausentes permanecen vacíos. Las diez fichas de demostración se conservan para no romper reservas y favoritos anteriores.

## Actualizar

Desde `backend/`, con la API detenida si hay migraciones pendientes:

```powershell
..\.venv\Scripts\python.exe -m scripts.sync_restaurants
```

Hace una consulta por comunidad autónoma, valida las respuestas y después aplica migraciones e importa ambas regiones en una transacción SQLite `BEGIN IMMEDIATE`. La caché JSON dura 24 horas. Explorar, filtrar y reservar usan SQLite; no consultan Overpass. `--region Madrid` o `--region Navarra` limita la actualización. `--offline` reutiliza snapshots sin red. `--force` fuerza una actualización manual; no usar en bucle. Si el servidor principal falla puede elegirse explícitamente otra [instancia pública documentada](https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances):

```powershell
..\.venv\Scripts\python.exe -m scripts.sync_restaurants --endpoint https://overpass.private.coffee/api/interpreter
```

La importación inicial se obtuvo con esa instancia alternativa después de un HTTP 502 del servidor principal. No hay reintentos automáticos ni consultas por movimiento del mapa. Respetar las [condiciones de uso del servicio público](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html); una distribución amplia requiere infraestructura propia o proveedor adecuado.

## Identidad, conservación y procedencia

Los identificadores son `osm-node-<id>`, `osm-way-<id>` o `osm-relation-<id>`. Se actualiza por `(source, external_id)`, sin borrar fichas, favoritos, borradores, orden, configuración o workspace. Las fichas incluidas en ejecuciones READY/RUNNING/WAITING_FOR_USER no se modifican durante la actualización. No se cambia el ID de una ficha existente. Las bajas de OSM no se eliminan automáticamente: la copia local requiere actualizaciones y revisión, y puede quedar desactualizada.

Cada snapshot guarda consulta, instancia, fecha de descarga, atribución, licencia y respuesta de origen. Los archivos `data/overpass-*.json` son locales y están ignorados. La base y las copias de seguridad tampoco se versionan. Antes de la primera migración se creó `.tools/backups/booking-pre-catalog.db`.

Los contratos añaden `source_url`, `data_attribution` y `data_license_url`; el frontend muestra crédito y enlace al objeto original. La atribución de datos es **© OpenStreetMap contributors**, [ODbL 1.0](https://www.openstreetmap.org/copyright). Si se redistribuye la base derivada deben respetarse las condiciones de esa licencia.

## Datos que no se infieren

Teléfono, web, dirección, cocina y opciones de menú solo se leen de etiquetas explícitas. No se inventan municipio, precio, valoraciones, fotografías ni opiniones. Los enlaces web se validan como HTTP(S), sin credenciales. No se utilizan etiquetas `image` de OSM como permiso de reproducción: las fotografías siguen pasando por el proveedor independiente de imágenes verificadas, con identidad, licencia y evidencia de derechos. La importación inicial no incorpora fotos.

`dietary_options` indica opciones declaradas (`vegetarian`, `vegan`, `gluten_free` con valor `yes`/`only`), no seguridad ante alergias. `cuisine_group=asian` agrupa cocinas documentadas; los filtros repetidos de cocina siguen siendo AND. Sushi/ramen se normalizan como cocina japonesa; pizza como italiana y pizzería. No se deduce cocina americana de una hamburguesería.

## Consulta desde el frontend

Se amplía `GET /api/restaurants`; no hay endpoint de búsqueda duplicado:

```text
?region=Madrid&catalog=auto&bbox=-3.72,40.40,-3.68,40.44&limit=100
?region=Navarra&catalog=real&q=Pamplona&cuisine_group=asian
?catalog=real&dietary_options=vegetarian
?catalog=simulated
```

`catalog=all` es el valor por defecto compatible con clientes existentes. `real` excluye demostraciones; `simulated` las muestra. `auto` utiliza reales si hay alguno en la región, independientemente de los demás filtros; si no, utiliza demostraciones. Una búsqueda real vacía no se rellena con datos ficticios. La UI usa `auto`, ofrece selector en filtros avanzados, consulta por área visible tras mover el mapa y pagina con 100 fichas en mapa/40 en listado. La búsqueda de texto consulta toda la región y considera nombre, dirección y municipio. La cola completa siempre se recupera del borrador.
