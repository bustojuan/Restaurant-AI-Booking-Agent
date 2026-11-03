# Pruebas y evaluaciones de IA

La batería ampliada supera **147 pruebas**, incluidas 12 de observabilidad. Se verifican replay sin ejecutar agentes/herramientas, persistencia después de reiniciar, aislamiento de contextos concurrentes, aprobación/interrupción, redacción, retención y autenticación administrativa. La evaluación offline conserva **15/15** casos sin solicitudes a modelos ni llamadas. Casos y alcance en [ADMIN_TESTING.md](ADMIN_TESTING.md).

La validación separa cuatro niveles: reglas/contratos, orquestación persistente, protocolo de voz y pruebas reales de proveedores. Pasar un nivel no acredita los siguientes.

Desde `backend`:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\ruff.exe check .
..\.venv\Scripts\ruff.exe format --check .
..\.venv\Scripts\python.exe -m alembic check
..\.venv\Scripts\python.exe scripts\evaluate_ai.py
```

La batería comprobada contiene **123 pruebas correctas**, incluyendo las 69 anteriores. Se usan SQLite en disco, checkpointing real, firmas del SDK y HTTP/eventos simulados. No requiere Internet ni claves. LangSmith está desactivado por defecto. Las deprecaciones emitidas por la dependencia LangSmith en Python 3.14 no se ocultan y no son fallos de prueba.

## Evaluaciones reproducibles

`app/ai/evaluations/scenarios.json` contiene 15 casos: confirmación, falta de plazas, alternativa válida e incompatible, corrección de hora, interrupción representada en texto, ambigüedad, depósito, evidencia alimentaria ausente, cuelgue, desconexión al confirmar, confirmación incompleta, cancelación, inyección de instrucciones y negativa a hablar con IA.

El runner crea bases temporales y fuerza extracción determinista, sin claves ni telefonía. Emite [docs/ai-evaluation-report.json](docs/ai-evaluation-report.json), con resultado por caso, comprobaciones objetivas y latencia medida de ejecución. Resultado observado: **15/15**, ninguna confirmación falsa respecto a los resultados esperados del dataset, **0 solicitudes a modelos y 0 llamadas telefónicas**.

`EvaluationAgent` comprueba prioridades, duplicados, un solo intento activo, correspondencia de confirmación e intento final, ausencia de llamadas posteriores y evidencia compatible con lo autorizado. La latencia del reporte mide el flujo local de fixtures; no es latencia de voz ni del modelo. La tasa de éxito del dataset no es una estimación de éxito con restaurantes reales.

## Persistencia y casos críticos

- El recorrido principal prepara el plan, investiga, ejecuta tres intentos, valida una restricción alimentaria, confirma el tercero y deja el cuarto sin contactar.
- Se reabre SQLite y el checkpointer tras una aprobación y una pausa. La decisión se recupera y no se duplica el contacto.
- Operaciones mutantes repetidas con el mismo ID devuelven el resultado previo. Una operación incierta no se vuelve a ejecutar automáticamente.
- El motor y las herramientas rechazan identidades ajenas, versiones obsoletas, permisos insuficientes y cambios en ejecución.
- Se comprueban nombre, identidad, personas, condiciones, contradicciones, pasos pendientes y ausencia de referencia sin inventar localizadores.
- Una cita del asistente no sirve como evidencia del restaurante. Un cambio posterior invalida una respuesta atrasada.
- Un timeout de contacto externo detiene la ejecución y requiere reconciliación; no pasa al siguiente restaurante.

## Voz y telefonía probadas sin proveedores

Los tests de voz ejercitan PCM16 y μ-law, startup de Live, audio concurrente con delegación, ID de delegación, replay, correcciones y errores. Otro test conecta ese transporte simulado con el grafo de delegación persistente real y comprueba que un sandbox no altera el borrador.

Los tests de telefonía verifican allowlist, caducidad, horario, presupuesto estimado, credenciales, dominio HTTPS, firmas, nonce, formato de audio, Call SID/cuenta, replay del stream, grabación desactivada y ausencia de rellamadas tras una respuesta de creación incierta.

No se han probado sonido de micrófono, altavoces, habla generada, calidad bajo ruido, latencia real, entrega de la presentación de IA ni llamadas de Twilio. Esas pruebas son opt-in y requieren claves, habilitación y autorización de coste. No hay un test automático que marque como correcto un proveedor real sin haberlo utilizado.

Para probar voz, seguir [VOICE_ARCHITECTURE.md](VOICE_ARCHITECTURE.md). Para una llamada controlada a un número propio, seguir [TELEPHONY_SETUP.md](TELEPHONY_SETUP.md). Las pruebas reales quedan pendientes hasta disponer de credenciales y una autorización concreta.
