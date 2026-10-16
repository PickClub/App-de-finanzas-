# C3 — Prototipo aislado de mantenimiento atómico

Estado: APTO para pasar al diseño de integración; NO es autorización de integración
ni evidencia de endpoints productivos instrumentados. R4 no se activó.

## Arquitectura experimental

`c3_history_keys_atomic.py` es un adaptador síncrono sintético. Reutiliza el modelo
del contrato aprobado, que genera fecha mediante el parser C3 canónico. Las claves
se incluyen en el mismo insert que el movimiento; las ediciones se calculan desde
el documento final leído dentro de la transacción y se incluyen en el mismo update.
No conserva una proyección separada ni escribe fechas normalizadas sobre el original.

El adaptador exige una sesión con transacción ya activa. Solo el runner crea sesiones
y usa with_transaction con snapshot, majority y PRIMARY, equivalente síncrono de
las opciones existentes. No importa server.py, no modifica sus manejadores ni
introduce transacciones anidadas. No reproduce íntegramente todas las reglas
financieras de MoneyFlow: sus cuentas, recibos e intenciones son exclusivamente
sintéticos y no reemplazan los contratos de idempotencia reales.

Generar claves ready o unverifiable es independiente de aceptar un gasto según
las reglas financieras. Una fecha inválida aceptada en el modelo permanece literal
y produce unverifiable; corregir explícitamente fecha produce ready. El bloque no
entra en fingerprints ni payloads de intención. La sanitización pública se verifica
en el adaptador experimental, combinada con el saneador compartido existente;
los serializadores productivos todavía requieren integración futura explícita.

## Aislamiento y base retenida

Una sola base nueva creada durante esta tarea:
`test_c3_history_atomic_0ddd0c9ec55640398679cb91088fde01`.

Destino estático sin credenciales:
`mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true`.

Antes de escribir se validaron URI, dirección efectiva, PRIMARY, replica set,
sesiones, protocolo compatible y ausencia del nombre mediante listDatabases
filtrado exactamente. Solo se crearon accounts, transactions, receipts y
synthetic_intents en esa base. No se creó ningún índice explícito: MongoDB crea
sus índices _id normales al crear colecciones. No se provisionó financial-context,
no se realizó backfill y no se utilizaron las bases P1/P2/P3 o MoneyFlow.

El auditor registra comandos y detecta destinos no permitidos; no se considera un
cortafuegos de MongoDB. El aislamiento depende además del destino fijo, la
comprobación previa y el único handle de base entregado al adaptador. El auditor
prohíbe drop, createIndexes y consultas de otras bases. Comandos administrativos
limitados a hello, comprobación filtrada del nombre y gestión de transacciones/sesiones.

La primera ejecución aprobó 20 tests, pero su comprobación final rechazó
listCollections, que PyMongo ejecuta antes de create_collection dentro de la nueva
base. Se reprodujo ese falso positivo offline (1 fallo), se permitió únicamente
ese comando en el destino sintético y se repitieron las pruebas con identificadores
nuevos en LA MISMA base creada durante esta tarea. No se descartaron registros
de la primera ejecución ni se creó una segunda base. Se consultaron nombres con
prefijo exclusivo para recuperar el nombre de esa ejecución; no documentos de
otras bases. Se conservaron los registros de ambas ejecuciones.

## Rutas representadas e integración pendiente

| Escritura existente | Simulación y mantenimiento probado |
| --- | --- |
| create_transaction / update_transaction / delete_transaction | Insert conjunto, edición final, eliminación del documento con sus claves |
| create_debt_payment / edit_payment_movement / remove_payment | Gasto sintético, edición, anulación y recibo histórico |
| create_goal_contribution | Transferencia y efectos en ambas cuentas |
| delete_goal | Retirada de enlaces preservando movimiento/claves |
| pay_bill / delete_bill_payment / delete_bill | Gasto, anulación o retirada de seguimiento |
| create_recurring_record / delete_recurring_record / delete_recurring_payment | Gasto, eliminación o desvinculación/restauración administrativa |
| R4 register_shared_payment / change_shared_payment | Movimiento con cápsula original conservada, anulación y seguimiento |
| R4 register_shared_tracking | Restauración de enlaces sin nuevo movimiento; mark administrativo sin efectos financieros |
| reference_integrity.coordinate | Incremento de revisión sin recalcular claves |

Estas son operaciones representadas por el modelo, NO llamadas a los endpoints
ni pruebas de sus políticas R3/R4 completas. La restauración sintética verifica
mantenimiento de claves, no elegibilidad financiera de link. La política de
presupuestos, siguiente período, sobrepagos y asociaciones sigue en producción
sin cambios, y debe probarse específicamente antes de integrar el adaptador.

## Evidencia ejecutada en esta tarea

- Primera ejecución: 20 tests MongoDB aprobados; validación final del auditor falló
  por el falso positivo de listCollections. No contabilizarla como ejecución completa.
- Ejecución validada: 22/22 escenarios MongoDB aprobados; 2 escenarios adicionales
  aprobados, total 24 distintos. No hay fallos financieros ni violaciones de destino.
- Auditoría después de los primeros 22: 50 movimientos retenidos de ambas ejecuciones,
  46 ready y 4 unverifiable, todos coherentes con sus fuentes. El escenario adicional
  de confirmación perdida valida por separado su movimiento; mark no crea movimiento.
- Concurrencia real de edición: dos callbacks iniciales leen la misma revisión;
  MongoDB aborta uno y with_transaction lo reintenta. Intentos observados: 2 y 1;
  importe final 72, saldo 928 y claves del documento final.
- Observador durante una edición no confirmada ve íntegramente el estado anterior;
  después del commit ve importe 99, saldo 901 y claves actualizadas.
- Mismo ID e intención concurrente: un movimiento y un descuento; payloads distintos
  con el mismo ID: una confirmación y un conflicto, sin escrituras parciales.
- Dos intenciones distintas de igual importe: dos movimientos legítimos, saldo 860.
- Dos anulaciones concurrentes y reintento tardío: devolución una sola vez,
  movimiento eliminado y recibo annulled conservado; no recreación del pago.
- Fallos provocados después de movimiento, saldo y recibo: snapshot completo
  idéntico al anterior tras abortar. También rollback de edición, anulación y
  transferencia cuyo segundo extremo falta.
- UnknownTransactionCommitResult: se inyecta después de un commit REAL; el driver
  repite commit y NO el callback. Otra prueba mantiene incertidumbre en la capa
  aplicación y la concilia manualmente sin nuevas escrituras.
- Reinicio simulado: nueva instancia del adaptador y recuperación del mismo ID y
  payload serializado, incluido date:null. No se reinicia MongoDB ni Expo.
- Retirada/restauración mantiene gasto, saldo y claves; mark con settles no mueve
  dinero. Los journals usados son propios del experimento, nunca R4/R6 reales.

Los fallos de conexión/commit se inyectan en el cliente. No se utilizaron failpoints,
no se apagó MongoDB ni se alteró la red del servidor. Los conflictos concurrentes de
escritura, transacciones, commits y rollback sí se ejecutaron en MongoDB real.

Suite offline final: 102 tests, 96 aprobados y 6 fallos históricos esperados:
9 del adaptador, 25 del contrato, 26 P3, 7 P1, 10 P2, 12 lector C3 y 13 contratos
C3/R9. Los seis esperados son los tres del parser P2 y los tres de historial/resumen/
zona histórica ya documentados. No se modificaron ni ocultaron esas comprobaciones.

Informe JSON: `backend/experiments/results/test_c3_history_atomic_0ddd0c9ec55640398679cb91088fde01.json`.
Los comandos registrados de las ejecuciones validadas solo accedieron a admin y
esta base. Los 18 archivos anteriores se comprueban por SHA-256; no hay modificaciones
en archivos registrados, frontend, configuración ni código financiero productivo.

## Reproducción y limitaciones

Offline: `python3 -B -m unittest backend.experiments.test_c3_history_keys_atomic`.
MongoDB opt-in: `python3 -B -m backend.experiments.c3_history_keys_atomic_mongodb --run-mongo`.
Ese último comando crearía OTRA base nueva y la conservaría: necesita una nueva
autorización para ejecutarse después de esta tarea. No se permite reutilizar bases
de tareas anteriores ni eliminarlas automáticamente. El runner exige rama y HEAD.

Antes de producción falta instrumentar todos los escritores reales, comprobar
los fingerprints específicos, integración asíncrona, respuestas públicas completas,
commits inciertos de las rutas ordinarias, filtros y detección de escritores antiguos.
El prototipo no prueba desconexión real, reinicio físico del servidor/dispositivo,
rendimiento masivo ni un provisionamiento reversible del historial existente.
No deben deducirse estas garantías del éxito del modelo sintético.

Ningún bloque ready habilita lecturas indexadas automáticamente. Siguen pendientes
cobertura histórica, índices autorizados, saneamiento, coexistencia de despliegues,
activación por generación y rollback con lectores optimizados desactivados primero.
R4 sigue desactivado; no se modificaron journals ni reglas financieras existentes.
