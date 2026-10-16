# C3 — Adaptador APPLY restringido a validación sintética

Bloque 4E. Código preparado, ensayado exclusivamente con clientes/sesiones falsos.
NO se ha conectado MongoDB ni creado una base, colección, índice o bitácora real.
No existe CLI, endpoint o modalidad financiera real. Los módulos anteriores,
writers, journals R4/R6 y los experimentos permanecen intactos.

## Entrada explícita y límites de confianza

SyntheticMongoApplyAdapter(client, plan, permit, verifier) recibe un cliente ya
preparado por el futuro runner aprobado. No construye MongoClient ni abre conexión
al importar. La selección de handles Database/Collection es perezosa. No carga .env,
archivos de autorización, credenciales ni planes exportados automáticamente.

SyntheticPermit exige mode=synthetic_only, operación apply o reconcile, aprobación
explícita, nonce hexadecimal de 32 caracteres y ausencia de la base atestada de
manera independiente. El nombre debe ser exactamente test_c3_apply_<nonce>.
Authorization vincula el PLAN privado completo (no su informe), run_id/digest,
URI local exacta, base, UUID de movimientos, R6, usuario efectivo, versión,
generación, alcance, revisión de código, época de exclusión y vencimiento finito.
El permiso añade UUID físico de la colección administrativa.

Estos tipos Python NO autentican al operador ni prueban por sí solos la procedencia
de los datos. El nombre test_ y una marca copiada no demuestran aislamiento.
El runner futuro deberá comprobar ausencia antes de crear, insertar solo fixtures,
registrar UUIDs/R6 mediante preparación separada y entregar una aprobación externa
para ese destino concreto. No hay carga automática ni modo que admita una base
financiera genérica. Un llamador privilegiado con acceso directo al cliente queda
fuera de la frontera que esta interfaz puede proteger.

## Exclusión externa obligatoria

verifier.verify(permit, deadline) debe comprobar de forma independiente la evidencia
aprobada y devolver Observation vinculada al Target/época exactos: escritores y DDL
excluidos, metadata estable, unicidad global comprobada y cero duplicados.
Sin proveedor, discrepancia o evidencia negativa, no se permite la primera escritura.
No se proporciona un verificador por defecto que devuelva true, ni se interpreta
la bitácora/registro de ejecución como prueba de exclusión.

Los falsos solo simulan esta comprobación. Antes de cualquier ensayo real se debe
autorizar y validar el proveedor externo, delimitar la ventana, controlar procesos,
operaciones en vuelo, modificaciones de metadata y DDL. MongoDB no elimina estas
exigencias ni excluye escritores externos por existir un registro administrativo.

## Preparación separada requerida

En la futura base nueva se necesitan previamente:

- transactions, con UUID aprobado.
- history_apply_synthetic_journal, con UUID aprobado.
- Metadata R6 financial-context válida y UUID esperado independiente.
- Marca c3-synthetic-apply-preparation con mode, nonce, UUID de movimientos,
  UUID de bitácora y environment_id exactos.

El adaptador no crea colecciones ni índices. La marca prueba coincidencia con la
preparación aprobada, no autenticidad del historial. Únicamente se utilizaría el
índice _id_ automático de la colección administrativa no fragmentada.

## Sesiones y actualización conservadora

La interfaz es compatible con apply_plan sin modificar history_apply.py.
Cada intento abre su propia sesión y transacción, usando snapshot, majority,
PRIMARY y max_commit_time_ms acotado. Nunca introduce transacciones anidadas ni
usa el antiguo atClusterTime de PLAN para escribir. Relee el documento vigente.

Antes de escrituras revalida loopback 127.0.0.1:27018, PRIMARY, replica set
app_finanzas_dev_rs, MongoDB 8.0, UUID de movimientos/bitácora y marca de preparación.
R6 se comprueba también dentro de la sesión. No se autoaprueban UUID leídos.
Los nombres de colecciones y comandos se construyen internamente. No existe API
que acepte pipeline, operadores o namespace de escritura del llamador.

read compara BSON físico tipado y precondiciones mediante validate_intent.
stage solo acepta el BSON exacto que read conservó y Evidence completa esperada.
Deriva nuevamente ready y compara el bloque aprobado. El CAS incluye _id,
usuario, _history_keys $exists:false y expresiones internas de tipo/presencia/valor
para _id e id/user_id/date/amount. Valores se envuelven en $literal, sin interpretar
cadenas que empiecen por $. Se distingue ausente, null, Int32/Int64/double y demás
representaciones canónicas. El fingerprint no se sustituye por igualdad numérica.

Se ejecuta exclusivamente update_one con $set de _history_keys, upsert=False;
exige acknowledged=true, matched_count=1 y modified_count=1. Luego se inserta la
evidencia confirmada en la MISMA sesión/transacción. Un fallo del recibo revierte
la actualización. No se reemplaza el movimiento completo ni se añaden campos de
procedencia. No se actualizan recibos financieros, cuentas, saldos o journals.
Transacciones y sesiones no pertenecientes al adaptador no pueden entrar en sus
operaciones; reconcile no permite begin de escritura.

UUID se inspecciona con listCollections fuera del snapshot financiero. Esa lectura
NO bloquea una sustitución posterior de colección. La exclusión externa continua
de DDL es obligatoria; si no puede acreditarse, no se autoriza aplicar.

## Bitácora y propiedad de ejecución

Registro fijo _id=execution: contexto, nonce, UUIDs, R6, usuario, run_id/digest,
versión/generación, scope, revisión, época y owner privado aleatorio. Se inserta
con majority antes de iniciar modificaciones de movimientos. Un registro existente
bloquea otra ejecución/otro proceso: no hay upsert, lease, reemplazo o adquisición
por expiración. Una confirmación incierta de ese registro bloquea la ejecución.

Recibos _id=receipt:<clave determinista>: esquema exacto de Evidence. Se comparan
todos sus campos al leer, incluida identidad BSON, fuentes, propuesta, revisión y
época; campos adicionales o contradictorios bloquean. Su publicación es atómica
con las claves del movimiento. No se almacena documento financiero completo.

El registro coordina solo el adaptador, no los escritores ajenos. Una instancia
cerrada no vuelve a abrirse. Tras caída/reinicio se prohíbe retomar APPLY; únicamente
una instancia explícita operation=reconcile puede consultar recibos bajo el mismo
plan/autorización/contexto. Reconcilia un RunState pendiente proporcionado de forma
explícita; no reconstruye planes ni incertidumbre desde un informe agregado.
La recuperación durable/general de ese estado sigue pendiente y bloquea uso real.

## Errores y confirmación incierta

TransientTransactionError permite reintentar transacción completa solo conforme
al aborto transitorio del servidor. UnknownTransactionCommitResult tiene prioridad,
incluso si aparece junto a otra etiqueta. Error de conexión o fallo genérico después
de enviar commit se trata conservadoramente como UnknownCommit. Tras incertidumbre,
los siguientes intentos llaman únicamente commit_transaction de la misma sesión;
no rehacen stage ni comienzan otra transacción. Un error posterior no se convierte
en rollback demostrado. El controlador mantiene el pendiente al agotar presupuestos.

Un recibo coincidente confirma la aplicación ORIGINAL, no vigencia actual de claves.
Ausencia sigue incierta. DuplicateKey de bitácora no se acepta como éxito sin leer
la evidencia íntegra. No se resuelve cambiando run_id, digest o intención.
No hay REVERT, VERIFY, reparaciones o rollback global de confirmados.

## Recursos y limpieza

Se conservan presupuestos del controlador: 10.000 documentos, 1 MiB por documento
final más evidencia, 32 MiB procesados, 30 segundos, 5 segundos por transacción,
tres intentos transaccionales y tres llamadas de commit. El adaptador además limita
operaciones de driver a 10.000 y contabiliza bytes de documentos, metadata y recibos,
incluidos reintentos. CSOT limita cada llamada y maxCommitTimeMS limita commit.
El driver puede realizar reintentos internos: las llamadas del modelo no cuentan
por sí solas todos los comandos de red. El deadline prevalece sobre esa cuenta.

Lecturas por ID están acotadas a un documento, aunque el driver puede recibir un
BSON de hasta el límite MongoDB antes del rechazo de 1 MiB. No se afirma un límite
RSS o de paquetes equivalente al presupuesto del modelo. No hay disk spill.
El chequeo de digest existente puede ser repetido por documento: no se demuestra
escalabilidad masiva en esta etapa.

close intenta abortar solo transacciones cuyo commit no fue enviado y cerrar
sesiones/cliente con hasta dos segundos. Después de commit incierto no envía un
abort explícito. Si el driver mantiene in_transaction y end_session podría abortar,
se bloquea la limpieza de sesión y se informa fallo, manteniendo incertidumbre;
no se presenta cierre completo. El comportamiento real del driver ante ese caso
requiere ensayo sintético. Un fallo de limpieza nunca autoriza continuar.

## Evidencia disponible y validación posterior

Las pruebas usan exclusivamente objetos falsos; los cambios de documentos y
registro suceden en copias artificiales en RAM. No hay medición de latencia MongoDB,
retención, failover ni atomicidad de un servidor. El informe del controlador conserva
sus flags offline y ninguna salida habilita APPLY real o lecturas indexadas.

```bash
python3 -B -m unittest backend.tests.test_history_apply_mongodb_adapter backend.tests.test_history_apply -q
```

Antes de la futura ejecución se requiere autorización independiente de base nueva,
colecciones de preparación/bitácora y fixtures, comprobación administrativa de
PRIMARY/versión/replica set, proveedor externo aprobado, pins independientes,
comandos monitorizados, pruebas de CAS/rollback/commit incierto/cierre y hashes de
campos financieros antes/después. Conservar la base; no crear índices explícitos.
No se autoriza usar bases financieras o experimentales anteriores.


## Adaptación offline al laboratorio autenticado (sin ejecución MongoDB)

El perfil operativo propuesto está cerrado a 127.0.0.1:27019, replica set
moneyflow_c3_apply_test_rs, base test_c3_apply_7e62d1a31cc9 y nonce
7e62d1a31cc9. LabTarget es independiente de Target de desarrollo: su binding
incluye destino, autenticación c3_apply/SCRAM-SHA-256, UUID de transactions,
history_apply_synthetic_journal y moneyflow_metadata, R6, usuario financiero
default-user, versión y generación. default-user no representa autenticación
multiusuario. Los antiguos destinos de 27018 se conservan solo para los clientes
falsos de pruebas; el runner no los acepta como perfil de laboratorio.

LabSnapshotReader reutiliza el recorrido canónico y el mismo snapshot T, reemplaza
la comprobación de identidad de desarrollo y valida los tres UUID físicos.
El adaptador revalida dirección, PRIMARY, replica set, versión exacta 8.0.32,
usuario/rol autenticado y los tres UUID antes de las escrituras simuladas.
La marca de preparación del laboratorio también contiene metadata_uuid. No cambia
CAS, upsert=False, sesión financiera, recibos ni reglas de commit incierto.

lab_client_options produce opciones privadas, no un cliente: connect=False,
retryReads=False, retryWrites=False, selección/conexión 3 s, socket 5 s y pool 1.
Las opciones contienen una contraseña y nunca deben serializarse o registrarse.
LabCredentials oculta la contraseña en repr. load_lab_credentials es una lectura
explícita del archivo privado apply, fuera del repositorio; rechaza symlinks,
permisos inseguros y errores con un código fijo. No lee al importar ni desde CLI.

physical_pins_approved es una precondición, NO una prueba criptográfica de origen.
Offline solo pueden validarse representación BSON, distinción entre colecciones y
aprobación requerida: no es posible distinguir un UUID inventado de uno físico
por sus bytes. No se generan UUID ni se autoaprueban lecturas del servidor. En la
preparación futura, un proceso independiente obtendrá los UUID de listCollections
y aprobará el contexto; cada observación deberá coincidir con el catálogo real.

Pendiente: los roles actuales permiten find en metadata, pero el namespace
canónico es moneyflow_metadata. El cambio de permisos exige otra autorización.
No se modificaron roles, usuarios, infraestructura ni flags en esta adaptación.

ExternalExclusionVerifier y request_mongodb_execution siguen bloqueando toda
ejecución MongoDB. El cliente autenticado, los pins, la red y la bitácora no son
prueba de exclusión externa. Sin proveedor independiente validado, APPLY queda
prohibido. No hay factory conectada al runner ni APPLY, VERIFY o REVERT operativos.


## PLAN observador: candidato no es autorización de escritura

LabObserverTarget es un tipo independiente: fija el laboratorio y
c3_observer/c3_observer_limited, acepta pins BSON candidatos y valida R6 sin
atributos approved ni physical_pins_approved. Su binding distingue explícitamente
closed_observer_plan_v1 del destino de escritura. LabTarget.validate no se relaja.
El adaptador APPLY rechaza el destino observador y no existe conversión automática.

LabObserverSnapshotReader reutiliza inventario, páginas tipadas, duplicados,
validación de respuestas y presupuestos del lector registrado. Sustituye el manejo
de sesión: crea UNA sesión causal_consistency=False para toda la ejecución,
selecciona T en la lectura snapshot de moneyflow_metadata y fija atClusterTime=T
en las lecturas siguientes. Identidad, catálogo y autenticación se comprueban
usando esa misma sesión; las lecturas administrativas de catálogo son actuales,
no una afirmación de snapshot de DDL. Cada cursor conserva sesión/T y se cierra
sin terminar la sesión común. Esta termina una vez al salir, con cierre acotado.

build_observer_plan recibe un cliente observador ya configurado y run_id explícito,
no crea clientes ni lee credenciales. Construye el PLAN únicamente en memoria,
con T compartido y máximo 30 segundos para adquisición y recorrido, conservando
los límites registrados. ObserverPlanEvidence oculta el PLAN privado en repr y
solo produce un informe agregado. Limpieza fallida impide devolver evidencia
completa. Errores de adquisición se sanean con códigos fijos; no se imprimen
excepciones completas, documentos ni secretos. No ejecuta transacciones ni escribe.

Distinciones obligatorias:

- Identidad física verificada: el catálogo coincide con los UUID candidatos.
- Pins candidatos: hipótesis de destino para lectura, no autorización de escritura.
- PLAN observador: cobertura y clasificación a T; no vigencia garantizada después.
- Aprobación APPLY: decisión independiente con contexto, digest y permisos propios.
- Exclusión continua: evidencia externa de escritores y DDL, no aportada por PLAN.

El contexto R6 se valida a T; UUID y cuenta se vuelven a comprobar durante el
recorrido. Eso no acredita exclusión continua de DDL ni certificación financiera.
SnapshotTooOld, CursorNotFound, conexión fallida, respuesta parcial o exceso de
presupuesto impiden completitud. El ensayo real de esta nueva ruta sigue pendiente.
