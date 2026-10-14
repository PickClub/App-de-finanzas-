# C3 — APPLY conservador, modelo exclusivamente offline

Bloque 4D: `history_apply.py` orquesta adaptadores falsos. No contiene cliente
MongoDB, CLI, endpoints, almacenamiento, índices, colección administrativa ni
escritura real. Importarlo no abre conexiones o archivos. No modifica escritores,
reglas financieras, journals R4/R6 ni el contrato canónico de `_history_keys`.

## Entradas y autoridad

`apply_plan(adapter, plan, target, authorization, controller)` exige un objeto Plan
privado completo y elegible, nunca su informe agregado. Reutiliza validate_intent
y derive_history_keys. El digest se valida con las reglas del modelo existente;
no es firma ni prueba de aprobación humana. Authorization inmutable vincula run_id,
digest, Target exacto (URI aprobada, base, colección, UUID físico, R6, usuario,
versión/generación), alcance, revisión completa del código, época de exclusión,
aprobación explícita y caducidad finita según el reloj inyectado.

`default-user` representa identidad efectiva single_user, NO autenticación.
Authorization.approved es evidencia de un fixture. La autorización operativa,
credenciales administrativas y protección del plan privado quedan pendientes.
Ningún modelo falso demuestra permisos o disponibilidad transaccional reales.

Observation exige coincidencia de destino y época, escritores excluidos, DDL
excluido, metadata estable y cobertura global de unicidad con cero duplicados.
Se vuelve a comprobar al abrir cada intento, dentro de la transacción, antes de
commit y al terminar el recorrido. Una declaración de exclusión no bloquea al
servidor. Un lease no consultado por escritores tampoco lo haría.
El futuro adaptador deberá comprobar esa ventana de manera independiente, con
operaciones en vuelo terminadas, restauraciones/escritores externos y DDL
controlados. Los cambios posteriores a T se comparan de nuevo; T no se reutiliza
como snapshot de escritura ni hace vigente indefinidamente el plan.

## Protocolo del adaptador falso

- bind_controller: liga el controlador privado a esta ejecución y rechaza sustituirlo
  para eludir incertidumbre. No equivale a coordinación distribuida durable.
- observe: entrega observaciones simuladas de identidad, exclusión y unicidad.
- begin(deadline): crea una transacción falsa de un solo documento, sin anidamiento.
- receipt(key): lee evidencia administrativa por identificador determinista.
- read(physical_id): devuelve documento vigente dentro de esa transacción.
- stage(current_bson, proposed_bson, evidence): prepara únicamente el equivalente
  a `$set: {_history_keys: bloque}` y la inserción administrativa conjunta.
- commit: publica ambos o ninguno; detecta cambios concurrentes del documento.
- close(deadline): descarta staging no enviado y libera recursos. Después de un
  commit incierto, cerrar NO demuestra rollback ni autoriza repetir la transacción.

El protocolo presupone que el adaptador respeta estas operaciones; un adaptador
malicioso no está validado por una interfaz Python. Solo los falsos incluidos en
las pruebas están ensayados. No se importa código experimental.

## Precondiciones por documento

Se preserva `_id` BSON físico completo, incluidos Int64/subtipo Binary. Se compara
representación exacta, no igualdad numérica Python o MongoDB. validate_intent
recomprueba id/user_id/date/amount, presencia frente a null y fingerprint canónico.
Luego se deriva nuevamente, exige ready y compara BSON exacto de la propuesta.
Un bloque existente, incluso idéntico al propuesto o null, es conflicto cuando
no existe evidencia confirmada coincidente atribuible a esta intención.

Una intención válida mantiene el formato exacto del módulo canónico. No agrega
procedencia, recibos, revisiones o IDs administrativos al movimiento. El documento
final se construye desde la lectura de la sesión; nunca se reemplaza completo.
Cambios administrativos previos a la lectura se conservan. Cambios después de la
lectura producen conflicto/transacción abortada en el simulador, incluso ABA.
No se autorizan correcciones de fechas, importes, identidades, cuentas o tipos.
El fallback canónico de importe ausente/null sigue siendo solo ordenación; no
constituye validación financiera ni autorización para reparar fuentes.

## Evidencia e idempotencia

Evidence inmutable contiene clave determinista, run_id, vínculo de destino,
digest de plan/intención, identidad BSON física, fingerprint, propuesta exacta,
revisión, época y estado confirmed. La clave SHA-256 deriva del contrato, destino,
run_id e identidad física; se compara la evidencia completa, no solo el hash.
Cambios en payload/propuesta/aprobación producen conflicto, no otra intención.

El falso publica evidencia confirmed y claves en un punto atómico. No crea una
bitácora en MongoDB ni archivos. La colección propia, privilegios, índice de
unicidad y durabilidad necesitarán autorización y validación separadas.
Los identificadores, fingerprints y bloques son privados y no aparecen en el
informe. No se guarda documento financiero completo dentro de Evidence.
Una evidencia exacta recupera la confirmación ORIGINAL sin volver a escribir.
No acredita que el movimiento actual siga existiendo ni que sus claves sigan
vigentes; esa comprobación será responsabilidad de VERIFY independiente.

## Reintentos, incertidumbre y ejecución parcial

TransientTransaction es una excepción del falso que afirma aborto demostrado;
se reintenta la transacción completa con las mismas precondiciones. UnknownCommit
reintenta únicamente commit en el MISMO objeto de transacción. No vuelve a leer,
preparar o aplicar mediante otro intento mientras el commit siga incierto.

RunState conserva binding, intención pendiente privada y bloqueo de limpieza.
Al agotarse presupuesto de confirmación se detienen los siguientes documentos.
Un controlador nuevo no puede eludir la intención pendiente dentro del mismo
adaptador falso. La supervivencia de este bloqueo a reinicios NO está demostrada:
no hay persistencia ni bitácora operativa en esta etapa. Será un bloqueo obligatorio
para un adaptador real, antes de permitir cualquier reanudación tras caída.

`reconcile` es únicamente conciliación de recibos del falso, sin escrituras,
VERIFY ni REVERT. Exige la misma autorización/contexto/intención y evidencia exacta.
Ausencia conserva uncertain; discrepancia bloquea y conserva la intención. Solo
confirmación íntegra y limpieza satisfactoria permiten despejar el pendiente.
Una autorización caducada no se renueva automáticamente para conciliar.

Los documentos ya confirmados no se revierten cuando otro falla. El informe
puede ser confirmed, partial_confirmed_blocked, blocked o uncertain (este último
puede incluir confirmaciones previas). Los reintentos recuperan confirmaciones
originales y no duplican staging. Ningún estado certifica cobertura del historial.

## Límites y limpieza

Presupuestos máximos reducibles: 10.000 intenciones, 1 MiB por documento final más
evidencia, 32 MiB procesados contando reintentos, 30 segundos globales, 5 segundos
por transacción, tres intentos transaccionales y tres intentos de commit por intento.
No materializar el historial completo: solo plan acotado y un documento vigente.
La validación del plan existente puede recalcular su digest por documento; esta
versión offline no demuestra escalabilidad ni rendimiento de validación masiva.

El falso debe respetar el deadline que recibe; el orquestador comprueba límites
antes de stage/commit y al finalizar. Un commit confirmado tardío no se deshace:
se conserva evidencia y se bloquea continuación/completitud de ejecución.
finally intenta cerrar transacción y adaptador con deadline finito de hasta dos
segundos. Limpieza fallida bloquea nuevos intentos; si había incertidumbre, no
la borra. Los presupuestos BSON no garantizan RSS ni tiempos de red de MongoDB.

Informes: estado, conteos de confirmados/recuperados, códigos fijos y estadísticas
agregadas de intentos/bytes. No contienen documentos, IDs, URI, fechas financieras,
importes, propuestas ni excepciones. Siempre offline_simulation=true y
coverage_complete_asserted=false, financial_correctness_asserted=false,
certificate_issued=false, indexed_reads_allowed=false. No conceden permiso operativo.

## Reversión y siguientes garantías

revert_policy delega el bloqueo canónico: no implementa REVERT. Igualdad de
fingerprints o recibo no prueba ausencia de escrituras intermedias. REVERT sigue
prohibido ante ABA, escritores desconocidos, pérdida de ventana continua o evidencia
insuficiente. Las revisiones del simulador son oráculos de test; no existen como
contador global de producción ni se añaden al movimiento.

Pendientes antes de una prueba MongoDB: diseño/autorización del adaptador separado,
base sintética nueva, transacciones reales snapshot/majority, CAS BSON exacto,
bitácora privada atómica, unicidad, contexto/UUID vigentes, control de escritores,
recuperación durable de incertidumbre y ensayos de fallos reales. PLAN/APPLY no
habilitan índices o lectores; VERIFY de todo el ámbito y continuidad de escritores
requieren otro bloque. Esta entrega no autoriza operaciones sobre datos reales.

## Ejecución offline

```bash
python3 -B -m unittest backend.tests.test_history_apply -q
```

Todas las modificaciones que realiza el adaptador de pruebas son sobre copias
artificiales en RAM. No existe CLI de APPLY, conexión, migración o bitácora persistente.
