# Telefonía: configuración y estado real

La instrumentación relaciona marcado, callback firmado, stream autenticado y sesión Live mediante IDs de llamada/intento/ejecución. Registra acciones autorizadas del backend, incertidumbre y reconciliación; la reserva de coste se distingue del gasto facturado. La lectura del histórico usa `ADMIN_API_TOKEN`, independiente de la autorización de llamadas. Ninguna consulta administrativa inicia telefonía. Ver [ADMIN_API.md](ADMIN_API.md).

Se investigó primero [Twilio Agent Connect y sus llamadas salientes](https://www.twilio.com/docs/conversations/agent-connect/initiate-outbound-conversations), incluida su [integración Python de GPT-Live](https://github.com/twilio/twilio-agent-connect-python/blob/main/getting_started/examples/partners/openai_gpt_live.py). Es una opción compatible; esta implementación utiliza el puente de Media Streams para controlar explícitamente la delegación, el buzón persistido y la autorización de aceptación del motor.

El transporte implementado usa [Twilio Bidirectional Media Streams](https://www.twilio.com/docs/voice/media-streams), el [recurso Calls](https://www.twilio.com/docs/voice/api/call-resource) y GPT-Live por WebSocket. También se comprobó la opción [SIP de GPT-Live](https://developers.openai.com/api/docs/guides/voice-sip); no se ha habilitado ni implementado SIP saliente directo. No se presupone acceso a esa función en una cuenta.

## Estado comprobado

Diagnóstico local sin conexiones ni exposición de claves o números: `python -m scripts.voice_preflight`. Devuelve las variables ausentes o inválidas y distingue configuración preparada de audio o llamada realmente validados. Antes de habilitar servicios, completar la configuración en `.env` local; no pegar credenciales en el chat. El informe actual indica ausencia de credenciales, allowlist propia, origen de gateway y tarifas.

- Código de llamadas salientes, cierre, firma de webhooks, autenticación del stream y asociación de identificadores implementado.
- Protocolo Live y solicitudes Twilio comprobados con dobles de transporte, bytes de prueba y HTTP simulado.
- **Ninguna llamada real realizada**. No hay credenciales OpenAI ni Twilio configuradas en el entorno revisado.
- La compatibilidad de cuenta, acceso al modelo, audio real, firma a través del túnel y cierre real por el operador deben verificarse con un número propio. No presentar los tests offline como una prueba de telefonía real.

## Separación de red

La aplicación de negocio escucha localmente en `127.0.0.1:8001`. El gateway es otra aplicación FastAPI, con únicamente:

```text
POST /twilio/status/{session_id}
WS   /twilio/media
```

No expone reservas, Swagger ni el token local. Para desarrollo, iniciar `python -m app.voice.gateway` en `127.0.0.1:8002` y configurar un túnel HTTPS/WSS **solo para ese puerto**. `TELEPHONY_PUBLIC_ORIGIN` debe coincidir con el origen público exacto. El operador mantiene el túnel y su control de acceso; este proyecto no lo crea ni publica nada automáticamente.

Las peticiones se verifican con `X-Twilio-Signature` contra el origen configurado. El stream exige además un nonce aleatorio por intento, cuenta, Call SID, formato de audio y sesión esperados. Solo se admite una conexión por intento; no se reconecta una llamada automáticamente. Se contemplan las variantes de esquema HTTP/WSS y barra final del handshake descritas en la [guía de seguridad de Twilio](https://www.twilio.com/docs/usage/security).

## Habilitación manual de la primera prueba

1. Completar las pruebas offline y del sandbox. Preparar un número propio donde una persona autorizada interprete al restaurante. No usar teléfonos de establecimientos reales para esta primera validación.
2. Instalar dependencias y aplicar `python -m app.migrate`. Configurar en `.env`: `OPENAI_API_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, origen HTTPS público y `TELEPHONY_ALLOWED_NUMBERS` como array de números propios E.164.
3. Verificar en Twilio que el número emisor está autorizado y que la cuenta permite el destino. La allowlist y `own_test_numbers_only` son una declaración del operador; el backend no puede demostrar la propiedad del teléfono destino.
4. Crear una solicitud de prueba con una ficha cuyo teléfono coincida exactamente con el número propio permitido. Con una única entrada en la allowlist, `python scripts/prepare_own_number_test.py --prepare-own-number-fixture` crea un borrador y una ficha nueva etiquetada como prueba en número propio. No modifica las fichas originales ni las reservas existentes y no realiza llamadas. Los restaurantes mock originales no tienen teléfonos; no se buscan ni inventan números externos.
5. Configurar horarios permitidos en Europe/Madrid, duración, número máximo de llamadas y tarifas conservadoras. Se exigen `TELEPHONY_COST_PER_MINUTE`, `LIVE_COST_PER_MINUTE` y `REASONING_RESERVED_COST_PER_CALL`; no se infieren precios. La reserva de gasto es una estimación conservadora, no una garantía del importe facturado por los proveedores.
6. Iniciar la API y el gateway, comprobar el túnel y activar `REAL_TELEPHONY_ENABLED=true` manualmente. Reiniciar ambos procesos. Mantener las credenciales solo en el servidor.
7. Iniciar la solicitud con versión y autorización explícita:

```json
{
  "mode": "real_telephony",
  "scenario_id": "confirm-first",
  "call_authorization": {
    "explicit_authorization": true,
    "own_test_numbers_only": true,
    "audio_processing_consent": true,
    "max_calls": 1,
    "max_duration_seconds": 120,
    "max_estimated_cost_eur": 3,
    "expires_at": "<fecha futura ISO 8601 con zona horaria>"
  }
}
```

Enviar a `POST /api/bookings/{id}/start`, con token local e `If-Match`. `scenario_id` se conserva por compatibilidad del contrato existente; en modo real no determina las respuestas del restaurante. La autorización y la cola se validan antes del inicio y otra vez antes de cada llamada. La configuración del servidor limita además la duración. No hay reintentos automáticos del POST de Twilio.

8. Escuchar y verificar presentación como IA, turnos, interrupciones, alternativa, depósito, rechazo y cierre. Confirmar por separado los eventos del backend, el estado del operador y lo que realmente oyó la persona. Solo tras esa revisión considerar otras pruebas explícitamente autorizadas.

## Incertidumbre, aprobación y cancelación

El Call SID de Twilio y el ID de sesión Live se guardan por intento. Un timeout ambiguo al iniciar una llamada produce `UNCERTAIN`; nunca se marca simplemente como un fracaso que autorice llamar al siguiente. Una llamada anterior debe estar terminada antes de avanzar. Una posible confirmación sin reconciliar detiene la reserva.

Las propuestas económicas requieren la decisión REST del usuario. La espera telefónica está limitada por `APPROVAL_WAIT_SECONDS`, la duración de sesión y el límite del operador. Si caduca, se detiene la ejecución y se solicita el cierre, sin aceptar automáticamente. Una aprobación posterior no revive una llamada terminada.

`POST /bookings/{id}/cancel` solicita el cierre de transporte. El gateway cierra Live y pide el hangup a Twilio; si no se puede acreditar el cierre, conserva la incertidumbre. El límite de duración enviado al operador ofrece otro límite de transporte cuando el proceso local falla; debe verificarse en la prueba real.

`GET /api/voice/bookings/{id}/calls` permite inspeccionar IDs, estados y reserva de coste. `POST /api/voice/calls/{call_id}/reconcile`, protegido por token y versión, consulta el estado del operador. Solo una atestación explícita `no_reservation_verified_by_user=true`, con la llamada terminada y destino coincidente, resuelve negativamente la reserva incierta. No la vuelve a llamar ni reinicia el booking. La herramienta no se expone a agentes.

Si falta el Call SID por una respuesta de creación perdida, la reconciliación automática no está disponible: localizar la llamada original en Twilio y revisar el resultado con la persona antes de preparar otra ejecución. Si se descubrió una reserva positiva tras una pérdida de conexión, requiere revisión de su evidencia y gestión manual; el endpoint no convierte esa atestación en una confirmación automática.

## Privacidad y transparencia

La grabación está desactivada y el sistema no guarda audio ni conversaciones completas. Sí procesa voz y transcripciones provisionales para delegar; las evidencias estructuradas y citas breves necesarias tienen retención limitada. `store=false` controla la opción de almacenamiento de la API utilizada; no sustituye la revisión de las políticas de tratamiento de los proveedores.

La presentación de IA es parte del diseño, en consonancia con las [obligaciones de transparencia del artículo 50 explicadas por la Comisión Europea](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act). Antes de usarlo con terceros deben revisarse la base jurídica, información, minimización, tratamiento de necesidades alimentarias y proveedores conforme al [RGPD](https://eur-lex.europa.eu/eli/reg/2016/679/oj). Una casilla de consentimiento técnico no acredita por sí sola el cumplimiento de esas obligaciones.

Las memorias caducadas se purgan; trazas y checkpoints antiguos de ejecuciones terminadas se limpian según `AI_RETENTION_DAYS`, preservando llamadas inciertas. La eliminación explícita de datos AI está disponible; no borra automáticamente el historial de negocio preexistente. LangSmith permanece desactivado salvo activación consciente, con revisión de datos y coste.
