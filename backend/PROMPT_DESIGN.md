# Diseño y versiones de prompts

Los eventos normalizados incluyen versión y SHA-256 del prompt base correspondiente a la ejecución. No copian el briefing personalizado, los mensajes del modelo ni razonamiento privado. Modelo configurado y modelo reportado se conservan por separado cuando existen. Esta instrumentación conserva las versiones actuales de los prompts porque su contenido no ha cambiado; el grafo tiene además su propia huella histórica. Véase [OBSERVABILITY_DATA_MODEL.md](OBSERVABILITY_DATA_MODEL.md).

Los ocho prompts están en `app/ai/prompts/`: `supervisor.md`, `planning.md`, `research.md`, `voice.md`, `negotiation.md`, `verification.md`, `memory.md` y `evaluation.md`.

Cada archivo declara `version: 1.0.0`. Al crear la ejecución se guarda una copia con versión y SHA-256, de modo que editar un prompt no cambie silenciosamente una ejecución ya iniciada. Los adaptadores usan esa copia. La API devuelve los identificadores de versión, no todos los textos ni los datos personales del contexto.

El prompt de voz cubre identidad de IA, estilo breve en español, escucha, interrupciones y cuándo solicitar ayuda. Conserva las secciones de política conversacional y utiliza el marcador de delegación indicado por la [documentación oficial de GPT-Live](https://developers.openai.com/api/docs/guides/live-prompting). Las reglas detalladas, permisos y validación de ofertas permanecen en el backend.

El contexto de una llamada se incorpora de forma separada al prompt general. En Responses, las instrucciones y requisitos van en mensajes de sistema/desarrollador; el habla recibida se trata como datos externos en un mensaje de usuario. No se concatena indiscriminadamente todo el historial. Se utiliza una ventana acotada y no se envía el teléfono de contacto al extractor.

Las salidas generativas se validan con Pydantic. Si falta una oferta completa, se pide aclaración. La ausencia de evidencia no se sustituye por los deseos del usuario. Los prompts de extracción exigen citas breves de los hechos confirmados; el código comprueba que provengan del restaurante.

Un prompt expresa comportamiento; no concede autoridad. Aunque un interlocutor diga que debe ignorarse la solicitud o aceptar un depósito, las herramientas y servicios mantienen sus límites. Los tests comprueban rechazo de instrucciones externas, correcciones, evidencias incompletas y autorización económica.

Para modificar un prompt, actualizar su versión, ejecutar evaluaciones offline y comparar resultados. Las pruebas con modelos reales y audio deben ejecutarse después y por separado: pasar fixtures deterministas no acredita una voz natural ni resistencia general a cualquier ataque.
