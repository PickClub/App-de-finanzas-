# C3 — Mantenimiento de claves en movimientos ordinarios

Alcance integrado: POST /api/transactions y la rama ordinaria de PUT
/api/transactions/{tid}, exclusivamente expense, income y transfer. No se
instrumentaron loan_given/loan_received, pagos de deudas, facturas, metas,
recurrencias, anulaciones ni rutas R4. Los rechazos existentes para movimientos
vinculados siguen vigentes. R4 permanece desactivado y no hay lectura indexada.

## Control explícito, desactivado por defecto

`MONEYFLOW_HISTORY_KEYS_WRITE_ENABLED` acepta 0/1, por defecto 0.
Para habilitarlo se exige `MONEYFLOW_HISTORY_KEYS_GENERATION`, entero positivo
BSON int32. No se inventa una generación al arrancar ni se crea un documento de
provisionamiento. Sin habilitación, generation puede estar ausente. No se cambió
ningún .env ni se habilitó el control fuera de los fixtures sintéticos.

La generación elegida en pruebas es 1. Cualquier activación local o de otro
despliegue requiere autorización posterior. Este control todavía no significa
cobertura completa: no permite activar lectores indexados.

## Escrituras y compatibilidad

POST mantiene la fijación de ID y fecha previa al callback, validaciones C4,
ordinary_transaction R1 y recomputación de saldos. Cuando el control está activo,
with_history_keys deriva del documento definitivo y sus metadatos forman parte
del mismo insert_one y la misma sesión. La respuesta conserva el documento público
original; las claves no entran en cálculos financieros.

PUT utiliza INTERNAL_PROJ para su lectura dentro de la sesión, conservando las
claves necesarias para inspeccionar el documento completo. La lectura exterior
solo sigue seleccionando la ruta de pago/ordinaria existente. Después de aplicar
transaction_edit_payload y validate_transaction, combina current+payload y utiliza
history_update_fields. Campos financieros y fragmento privado se escriben en un
único update_one. No hay escritura posterior ni transacción anidada.

Omitidos y null conservan la semántica anterior: date:null del PUT conserva la
fecha previa según transaction_edit_payload; notas/cuenta explícitamente null
siguen el contrato existente. No normalizar fechas almacenadas. Una fecha inválida
aceptada por la validación original produce unverifiable, sin un nuevo rechazo
financiero. Cambios administrativos no provisionan claves ausentes ni reparan
automáticamente bloques existentes. Un cambio real de fecha/importe puede generar
el bloque correspondiente al nuevo estado legítimamente editado.

Con el control apagado no se llama al generador ni se actualizan claves anteriores.
Si se edita una fuente de un movimiento que ya tenía claves, pueden quedar obsoletas:
ese riesgo exige mantener desactivada la lectura indexada hasta auditar cobertura
y todos los escritores. Cambiar a un tipo fuera del alcance puede igualmente dejar
claves antiguas sin mantenimiento; no se altera la regla financiera para evitarlo.

Las claves permanecen ocultas mediante los saneadores ya integrados. No se cambiaron
payment_transaction, ordinary_transaction, reglas de saldo, IDs, fingerprints,
recibos ni journals R4/R6. La edición de movimientos de pagos de deuda continúa
por edit_payment_movement sin generación de claves.

## Idempotencia y confirmación incierta

Los POST ordinarios NO admiten una clave financiera de idempotencia. Dos POST
independientes iguales producen dos movimientos legítimos, como antes. No prometer
deduplicación de un POST manual después de perder su respuesta. Los reintentos
internos de una transacción abortada conservan ID y fecha; el PUT repetido de un
mismo movimiento no crea una segunda fila ni aplica doble descuento.

UnknownTransactionCommitResult continúa respondiendo 503 con incertidumbre; no
reintenta automáticamente el POST ni afirma rollback. Una prueba inyecta la pérdida
de confirmación después de un commit REAL y verifica movimiento+claves+saldo juntos.
No se apagó el servidor, no se alteró la red ni se utilizaron failpoints.

## Pruebas y aislamiento

Memoria primero: 18 pruebas específicas (configuración y rutas ordinarias), más
44 pruebas del módulo/saneamiento previo, todas aprobadas. El primer fixture de
configuración omitía CORS_ORIGINS requerido: se corrigió el fixture, no la política
de CORS. La expectativa del arnés que prohibía cualquier settings se actualizó
para permitir únicamente los dos valores sintéticos del control, sin load_settings,
startup o .env. No se modificaron los 23 archivos experimentales anteriores.

Regresión final: 407 tests backend en memoria, 404 aprobados y 3 fallos históricos
esperados C3/R9. Experimentales offline: 77 tests, 74 aprobados y los 3 fallos
esperados del parser P2. Los 13 scripts frontend, TypeScript y git diff --check
aprobaron. No se ejecutaron las suites externas que crean datos en un servidor
configurado ni las suites MongoDB anteriores con limpieza automática.

MongoDB real: versión final 15/15 escenarios aprobados en
`test_c3_ordinary_keys_b993633efa054d0692e47ffe0e54c04d`.
La ejecución anterior de 14 escenarios utilizó
`test_c3_ordinary_keys_fd69fac7cc3340269d29a99fcd2f4449` y aprobó 14/14.
Se conservan AMBAS bases: la segunda se creó para validar el alcance final que
excluye expresamente loan_given/loan_received. No se reutilizó ni consultó la primera.

Destino exclusivo de pruebas:
`mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true`.
Cada ejecución verifica PRIMARY, sesiones, replica set, dirección y ausencia del
nombre nuevo mediante listDatabases filtrado. Colecciones por escenario dentro de
su única base sintética. Se registra que solo se accede a admin y esa base; no hay
drop, migración, índice explícito ni provisionamiento financiero. MongoDB crea sus
índices _id normales al crear colecciones de pruebas.

Escenarios incluyen gastos/ingresos/transferencias y ambos saldos, edición de
fecha/importe/cuenta, omitted/null, ready/unverifiable, control activo/inactivo,
historial sin claves, PUT repetido, dos POST legítimos, rollback completo después
de escribir, reintento transitorio conservando ID/fecha, pagos de deuda excluidos,
tipos loan excluidos y confirmación incierta después de commit real.

Concurrencia real: dos ediciones leen el documento original del movimiento en sendas
sesiones, se fuerza la intercalación y MongoDB provoca conflictos. En la ejecución
final se observaron 1 y 3 intentos, relectura vigente, claves sincronizadas y saldo
igual al inicial menos el importe confirmado. No se modificaron los reintentos
acotados del manejador compartido. Un fallo agotado mantiene su contrato de error.

Comandos offline:
`python3 -B -m unittest backend.tests.test_ordinary_history_keys backend.tests.test_history_keys`.

MongoDB opt-in:
`MONEYFLOW_C3_ORDINARY_KEYS_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_ordinary_history_keys_mongodb`.
Una ejecución futura crea OTRA base y necesita nueva autorización; nunca limpia
ni reutiliza bases anteriores.

## Pendientes antes de activación completa

- Instrumentar los demás escritores únicamente con autorización específica.
- Diagnosticar/provisionar historial mediante procedimiento separado y reversible.
- Índices y lectura optimizada requieren autorización independiente.
- No hay garantía nueva de idempotencia para POST ordinario; queda fuera del alcance.
- Medir coste de mantenimiento y validar físicamente solo con un entorno sintético.
- No integrar ni activar R4 como consecuencia de esta etapa.
