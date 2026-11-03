# Reconstrucción histórica sin reejecución

La animación identifica una invocación concreta, no un nodo que se haya visitado alguna vez. `graph-replay.ts` asocia la entrada con la última transición compatible anterior al inicio en la misma ejecución, versión y thread, y respeta el límite de la visita anterior. Si no hay entrada demostrable, no inventa una. Los caminos contraídos requieren su cadena observada. La actividad se indica con un punto móvil; las decisiones usan etiquetas `Si: …`, sin guiones ambiguos. Al retroceder se vuelve a calcular desde los eventos persistidos.

El número de invocación utiliza la historia completa cargada, aunque la cronología se filtre a un intento. Los especialistas del contacto se muestran dentro de Voice Session únicamente si hay spans descendientes conservados o correlación explícita con la llamada y su intervalo. Las revisiones posteriores del grafo conservan sus IDs originales y se etiquetan como revisión de oferta/confirmación. No hay migración ni reescritura de definiciones históricas.

La explicación del intento es una proyección actual de registros de negocio y se identifica separadamente del cursor histórico. Enlaces a ofertas, evaluaciones y confirmaciones muestran datos minimizados; los enlaces a eventos conservados seleccionan el cursor correspondiente. La ausencia de una captura o su purga no genera conversaciones, estados ni decisiones sintéticos.

1. Consultar la captura y comprobar su cobertura, fechas de instrumentación, eventos purgados y spans sin final.
2. Leer la primera página de `/api/admin/observability/events?execution_id=...` y conservar su `high_watermark`.
3. Paginar usando `after_event_id=next_after_event_id` y `until_event_id=high_watermark` hasta `has_more=false`.
4. Ordenar por `id` y cargar las definiciones indicadas por `graph_version`; no usar automáticamente la arquitectura instalada ahora.
5. Aplicar eventos a una proyección en memoria del panel: invocaciones por `span_id`, relaciones por padre/agente/herramienta/delegación y llamadas por intento/sesión.
6. Play, pausa, saltos y avance/retroceso recorren esa colección local de hechos. Ninguno requiere `ainvoke`, reanudar checkpoints, herramientas, llamadas o solicitudes a modelos.

La captura fija excluye eventos nuevos que lleguen mientras se pagina. Para volver a modo vivo se retoma el cursor por WebSocket/REST y se desduplica. La persistencia es la fuente de recuperación; un buffer de WebSocket no es el histórico.

`graph.transition.selected` permite resaltar la decisión observada. El siguiente nodo iniciado acredita su entrada; una selección sin entrada no se convierte en ejecución. Los nodos sin invocación no se marcan completados. Interrupción, cancelación, fallo y final normal son eventos distintos.

El índice de captura no decide si hay una reserva: la confirmación, la decisión humana y los resultados se enlazan con registros del motor. La duración monotónica de un span no se sustituye por diferencias entre relojes de proveedores. Sus timestamps originales sirven como información adicional cuando existen.

La política actual permite reproducir visualmente cronología, grafo, herramientas redactadas, decisiones y metadatos de conversación. No permite reproducir audio ni mostrar el texto completo de una conversación porque esos datos no se guardan. No se crean ondas, intervenciones, versiones, consumo ni finales que falten.

Una ejecución anterior a esta instrumentación puede conservar intentos/trazas antiguos sin grafo versionado ni spans completos. La consulta no los rellena con el flujo actual. Tras un fallo de proceso puede quedar un span abierto; después de la retención puede quedar solo el marcador de purga. Estas limitaciones deben ser visibles en el futuro panel.

Implementación de escritorio: [AI Control Center](../frontend/docs/control-center.md), `src/admin/replay.ts` y `Timeline.tsx`. Las lecturas de replay están separadas de la escritura de Playground.
