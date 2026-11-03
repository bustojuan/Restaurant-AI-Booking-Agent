# Verificación de observabilidad

La batería completa del backend supera **147 pruebas**. La ampliación añade 12 pruebas en `tests/test_observability.py`; también se conservan las pruebas de migraciones, motor, seguridad, agentes y protocolo de voz. Las comprobaciones utilizan SQLite en disco y transportes simulados. La suite pytest no inicia Electron; la validación visual del administrador se documenta al final.

```powershell
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m pytest -q tests/test_observability.py
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
..\.venv\Scripts\python.exe -m scripts.evaluate_ai
..\.venv\Scripts\python.exe -m scripts.export_contracts
```

Se comprueban:

- Tres intentos AI, agentes repetidos, jerarquía de spans/herramientas, transiciones reales, versiones/checkpoints, resultados y confirmación del backend.
- Simulación clásica sin agentes/modelos/grafos ficticios; ausencia de instrumentación anterior.
- Persistencia tras cerrar y abrir FastAPI, y replay con ejecución/proveedor bloqueados por el test.
- Snapshot de replay con cursor y límite fijo mientras llegan eventos nuevos.
- Interrupción por aprobación, decisión humana correlacionada y confirmación posterior.
- Contextos asíncronos concurrentes, fallos, cancelación y spans interrumpidos, sin copiar mensajes privados.
- Exclusión de datos personales, alimentación, credenciales, prompts dinámicos, respuestas habladas, audio y transcripción completa.
- Metadatos Live con socket falso: sesión, delegación, rol/provisionalidad, primer audio, uso recibido y ausencia de contenido.
- Token administrativo independiente, bloqueo del token ordinario, límites REST y replay autenticado por WebSocket.
- Retención, sandbox huérfano, marcador de purga, borrado AI por cascada y cursores que no se reutilizan.
- Fallo del almacenamiento de telemetría sin reintentar trabajo, y señal de pérdida cuando vuelve a escribir.

La evaluación offline conserva **15/15 escenarios**, sin confirmaciones falsas, solicitudes a modelos ni llamadas. Las pruebas de voz acreditan protocolo y metadatos con bytes sintéticos; no acreditan audio real, cuenta del proveedor o telefonía externa. Esas pruebas siguen pendientes por decisión del usuario. Los 13 avisos de deprecación de LangSmith/Python existentes no representan fallos de las pruebas.


## Control Center operativo

Se añaden seis pruebas en `tests/test_control_center.py`: historial/orden/filtros/grupos, lecturas sin ejecutar agentes, analítica persistida sin mezclar modos, Playground sin modificar workspace, acceso administrativo y proyección de settings sin secretos, y decisiones humanas que sobreviven a la retención de trazas. El escenario alimentario simulado no confirma sin verificación obligatoria. No se requieren migraciones adicionales.

[Verificación Electron y capturas](../frontend/docs/verification.md#ai-control-center-validación-final). Las pruebas de voz y telefonía reales continúan pendientes por decisión del usuario.
