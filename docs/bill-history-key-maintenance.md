# C3 — Claves privadas en pagos de Facturas

## Alcance y activación

Se instrumenta exclusivamente la inserción del movimiento del flujo heredado de
`POST /api/bills/{bid}/payments` (`pay_bill`). El selector compartido R4 sigue
anterior a esta rama; sus escritores no se instrumentan en este bloque.
`MONEYFLOW_HISTORY_KEYS_WRITE_ENABLED` permanece desactivado por defecto.
No se modifica configuración, .env, lectura indexada ni activación R4.

Después de fijar ID, usuario, fecha normalizada, importe y vínculos definitivos,
`with_history_keys` copia el documento final y prepara `_history_keys` según el
contrato común. El movimiento y las claves se insertan conjuntamente en el
mismo `insert_one` y sesión de `payment_transaction`. No hay escrituras
posteriores, transacciones anidadas, migraciones ni relleno histórico.

Con el control desactivado se inserta el mismo documento anterior sin llamar al
generador. Los recibos de Facturas y Recurrencias, facturas siguientes y journals
no reciben claves. La generación del siguiente período, coordinación R2/R3,
importes, saldos, IDs y fingerprint del payload original permanecen intactos.
Un reintento devuelve el recibo original sin regenerar claves ni movimientos.
La eliminación conserva el recibo anulado, devuelve el dinero exactamente una
vez y elimina el movimiento junto con sus claves. No se añade código al DELETE.
El saneamiento público existente conserva la exclusión recursiva de `_history*`.

## Verificación ejecutada

- Antes del cambio: 11 pruebas específicas en memoria, 5 fallos que demostraban
  ausencia de claves en el movimiento. Después: 13 pruebas específicas aprobadas.
- Suite backend offline: 435 casos, 432 aprobados y 3 fallos históricos esperados.
- Offline experimental: 77 casos, 74 aprobados y 3 fallos esperados del parser P2.
- 13 scripts frontend y TypeScript aprobados.
- MongoDB: ejecución final de 15 pruebas aprobadas en la base nueva
  `test_c3_bill_keys_bfce26552996401caefa2b95893ba8a2`.

El arnés verifica URI local, PRIMARY, replica set, sesiones y ausencia previa del
nombre antes de crear la base. Colecciones separadas por escenario; todas las
operaciones de datos quedan restringidas a la base nueva, con auditoría de
comandos. No se crean índices explícitos ni se eliminan bases.

Se comprobaron pagos independientes iguales, claves idénticas, conflicto de
payload, desactivación, generación mensual, recibos vinculados a recurrencias,
rechazo R3 por plantilla, tombstone y reintento tardío, rollback tras movimiento
/inserción/derivación/devolución, respuestas públicas, cancelación concurrente y
conflicto real entre pagos de $70 sobre $100 desde cuentas distintas. En ese
conflicto hubo reintentos con lectura actualizada y solo un gasto de $70.

La pérdida de confirmación se inyecta en el cliente del arnés después de un
commit real (creación y anulación). No equivale a un failpoint del servidor ni a
una interrupción física de red. El reintento original conserva los documentos
sin un segundo gasto o devolución.

La primera ejecución MongoDB detectó dos problemas exclusivos del arnés
(parámetro `expected` en lugar de `status`, y `findAndModify` ausente de la lista
de comandos permitidos). Se corrigieron únicamente en las pruebas nuevas.
Las bases de las ejecuciones previas de este bloque se conservan:
`test_c3_bill_keys_90341fdfbd7943879bf6bb7eccc2105c` y
`test_c3_bill_keys_0b8f707efaf64d989c7c8d10df97f185`.
No se reutilizaron ni consultaron en ejecuciones posteriores.

## Límites y pendientes

La ruta existente normaliza fechas mediante `_parse_dt` e `isoformat()` antes
de insertar; no se cambia ese contrato. Una fecha rechazada por la ruta sigue
siendo rechazada. La prueba `unverifiable` inyecta una incapacidad de verificación
del parser derivado, sin cambiar las fuentes financieras, para comprobar que
no introduce rechazos ni altera saldos. Las fechas heredadas inválidas no se
adoptan ni reparan.

La alternancia del control no garantiza cobertura completa o actualidad de
claves históricas; las lecturas indexadas siguen desactivadas. La instrumentación
de Recurrencias, Metas y núcleo R4 requiere autorización y etapas separadas.
No se realizó prueba física Samsung en este bloque.
