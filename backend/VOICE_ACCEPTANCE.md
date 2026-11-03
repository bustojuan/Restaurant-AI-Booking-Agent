# Validación de voz: preparación y aceptación real pendiente

Estado: **audio real y telefonía real pendientes**. Este documento no acredita conversaciones con un proveedor. Las pruebas automáticas usan sockets, audio binario y HTTP de fixtures; no escuchan sonido ni contactan con números reales. Configurar credenciales tampoco cambia este estado.

## Preparación sin conexiones externas

Desde `backend`, ejecutar `..\.venv\Scripts\python.exe -m scripts.voice_preflight`. Solo comprueba configuración: no imprime secretos ni números, no abre micrófono y no llama a proveedores. Incluye seis escenarios con estado `pending`.

Verificar primero los procedimientos existentes de [sandbox](VOICE_ARCHITECTURE.md) y [número propio](TELEPHONY_SETUP.md). No utilizar restaurantes del catálogo para pruebas. La allowlist debe contener exclusivamente el número propio autorizado; cada ejecución real necesita consentimiento, caducidad y límites explícitos de coste, duración e intentos. El panel administrativo continúa siendo de lectura y su Playground determinista no activa servicios de pago.

## Matriz para la sesión real autorizada

| Escenario | Ejecución controlada | Criterio que debe observarse | Evidencia mínima |
|---|---|---|---|
| Interrupción | La persona interrumpe mientras habla la voz | Se deja de reproducir la respuesta anterior; se atiende la corrección sin aceptar datos antiguos | Eventos de turno y orden temporal, revisión y resultado de la delegación; anotación del operador |
| Corrección | Corregir hora/personas mientras hay una consulta pendiente | La respuesta correspondiente a una revisión anterior no autoriza una aceptación; se aclaran los datos actuales | IDs de delegación/revisión y oferta final |
| Silencio | Mantener silencio y comprobar el límite configurado | La sesión termina dentro de los límites; no se fabrica oferta ni confirmación | Inicio/final, duración, transporte terminal y ausencia de confirmación |
| Alternativas | Ofrecer primero una hora fuera de ventana y después otra válida | La primera no se acepta; la válida sigue requiriendo evidencia explícita de confirmación | Oferta y evaluación, requisitos mínimos y confirmación vinculada al intento |
| Depósito | Solicitar una condición económica | WAITING_FOR_USER; sin aceptación hasta decisión persistida; comprobar aprobación, rechazo y caducidad en ejecuciones separadas | Oferta, evento de decisión y acción autorizada del motor |
| Pérdida de conexión | Cortar antes de propuesta y, en otro caso, durante aceptación/confirmación | Cuando puede existir reserva, parada y revisión; sin rellamada automática ni salto a otro restaurante; verificar cierre con proveedor | Resultado, transporte, referencias de reconciliación y contador de llamadas |

Registrar para cada caso el modo real utilizado, identificadores de reserva/ejecución/intento/sesión, timestamps disponibles, resultado esperado y observado, incidencias y quién comprobó el resultado. Distinguir `superado`, `fallido` y `no ejecutado`. Medir latencias reales sin trasladar tiempos del simulador. No guardar claves, teléfonos, audio ni conversaciones completas; usar metadatos y las evidencias mínimas autorizadas.

## Qué prueban las verificaciones automáticas

- `tests/test_voice_protocol.py`: PCM/μ-law con fixtures, audio concurrente con delegación, deduplicación, correcciones que invalidan respuestas atrasadas, errores, silencio acotado y desconexión sin reconexión.
- `tests/test_voice_graph_integration.py`: delegación con grafo persistente, procedencia de evidencias y timeout externo que detiene la ejecución.
- `tests/test_telephony_guards.py`: permisos, límites, firmas, identidad del stream, contrato HTTP y ausencia de rellamada ante creación incierta.
- `scripts/evaluate_ai.py`: escenarios de texto deterministas, incluidas alternativas, depósitos, interrupciones representadas en texto y confirmaciones incompletas. No mide calidad de conversación ni de audio real.

Ejecutar las pruebas offline no completa esta matriz real. El siguiente paso que depende del usuario es retomar una sesión autorizada con cuentas y número propio configurados. Las credenciales se introducen en `backend/.env`, nunca en el chat.
