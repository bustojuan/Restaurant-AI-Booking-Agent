# Agentes y herramientas

Cada invocación observada tiene `span_id` y, cuando existe, `parent_span_id` y `agent_run_id`. Las herramientas registran `tool_call_id`, entradas/salidas proyectadas y devolución idempotente; nunca copian requisitos, ofertas completas, datos de contacto o texto de conversación. Los nodos de coordinación se registran como nodos, sin presentarlos como agentes adicionales. Esquema: [TRACE_SCHEMA.md](TRACE_SCHEMA.md).

| Agente | Entrada y salida | Herramientas / límites |
|---|---|---|
| Supervisor | IDs y estado actual → ruta condicional | Estado, cola, siguiente restaurante y avance de un intento mediante el motor |
| Planning | Configuración → `BookingPlan` | Requisitos y cola; no inventa obligaciones ni altera la solicitud |
| Research | Restaurante → `ResearchResult` | Datos existentes y observaciones con fecha; distingue FACT, HISTORICAL y UNKNOWN |
| Voice | Briefing y audio → propuestas/evidencia | Conversación GPT-Live; delegación al backend, sin acceso a estados finales |
| Negotiation | Propuesta extraída → `NegotiationDecision` | `NegotiationPolicyService` valida los límites; no confunde oferta con confirmación |
| Verification | Oferta aceptada y evidencia → `VerificationResult` | Servicio de verificación; contradicción, identidad equivocada o datos incompletos impiden confirmar |
| Memory & Summary | Eventos → resumen y observaciones históricas | Sin audio ni transcripciones completas; preferencias solo con consentimiento expreso |
| Evaluation | Registros persistidos → `QualityReport` | Comprobaciones objetivas independientes; no modifica el resultado operativo |

No todos son LLMs: la coordinación, planificación, investigación y validaciones son deterministas. La extracción por Responses es el punto generativo opcional para lenguaje ambiguo; la voz utiliza su propio modelo. Cada responsabilidad tiene prompt, contrato y pruebas específicos.

## Catálogo de capacidades

Lectura: `get_booking_requirements`, `get_restaurant_information`, `get_booking_priority_queue`, `get_next_restaurant`, `get_current_call_context`, `get_booking_status`, `get_previous_attempts`.

Evaluación: `evaluate_alternative`, `verify_reservation`.

Mutación acotada: `persist_call_outcome` (avanza el motor una vez), `request_user_approval` (publica una propuesta económica para validación del motor), `submit_reservation_evidence` (evidencia ligada al intento) y `finish_call` (solicita cierre). No existe herramienta para aprobar en nombre del usuario, pagar, cambiar prioridades activas o escribir una confirmación directa.

`ToolScope` se construye desde el código confiable con ejecución, reserva, agente e intento. El modelo no elige estos IDs. La matriz `PERMISSIONS` restringe cada agente. Los argumentos usan Pydantic y rechazan campos extra. Las capacidades de lectura se exponen como `StructuredTool` de LangChain; las mutaciones requieren además un ID de operación suministrado por el coordinador y no se entregan como herramientas libres al extractor.

Cada llamada al registro de herramientas comprueba pertenencia y permisos, registra inicio/fin/error y aplica idempotencia en mutaciones. El grafo corto de delegación de voz registra también cada tarea delegada. El servicio de transporte solo publica propuestas o evidencia en su buzón; el motor vuelve a consultar el estado antes de aceptar o avanzar.

## Evidencia y datos no confiables

La extracción recibe instrucciones, contexto confiable e intervenciones externas en mensajes separados. No dispone de herramientas para ejecutar instrucciones del interlocutor. Las correcciones sustituyen resultados anteriores y una nueva revisión de la conversación invalida respuestas atrasadas.

Las condiciones económicas incluyen depósito y otras obligaciones en `financial_conditions`. Cualquiera requiere aprobación. En voz real se exige además una aclaración económica citada por el restaurante antes de enviar una propuesta al motor; no se interpreta silencio como ausencia de cargos.

Para evidencia real, el extractor exige citas que estén presentes en las intervenciones recibidas del restaurante; lo dicho por el asistente no cuenta como prueba. Los requisitos no citados pierden la marca de verificados. El servicio exige coincidencia de restaurante, intento, nombre, fecha, hora, personas y condiciones aceptadas. Un paso posterior, una duda o una contradicción producen `PENDING`, `AMBIGUOUS`, `NEEDS_USER_ACTION` o `REJECTED`, sin crear una reserva confirmada.

Estas comprobaciones reducen errores y se prueban con fixtures; no acreditan la calidad de extracción de un modelo real ni constituyen garantías alimentarias.

## Memoria y observabilidad

La memoria temporal vive en checkpoints. `AgentMemory` conserva observaciones históricas y preferencias autorizadas con caducidad; una preferencia guardada no cambia automáticamente ninguna reserva. Los resúmenes se basan en eventos e intentos persistidos, no en un relato generado sin evidencia.

`AgentTrace` guarda agente, herramienta, fase, latencia medida, modelo y uso de tokens cuando el proveedor los entrega. Los costes no observados se dejan nulos. La reserva conservadora de gasto telefónico se muestra separadamente del coste facturado. Los eventos `agent.activity` reutilizan el WebSocket existente y su cursor; exponen acciones y resultados breves, nunca razonamiento privado.

`GET /bookings/{id}/ai`, `/ai/state`, `/ai/traces` y `GET /voice/bookings/{id}/calls` permiten inspección. Las preferencias se gestionan en `/ai/memories`. `DELETE /bookings/{id}/ai/data` borra datos AI y checkpoints de una ejecución terminada, preservando el historial de negocio; una llamada incierta exige reconciliación antes de borrar su registro.
