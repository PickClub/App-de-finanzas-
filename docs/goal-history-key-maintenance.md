# C3 — Claves privadas en aportaciones a Metas

## Alcance

Solo se instrumenta `create_goal_contribution`, en
`POST /api/goals/{gid}/contributions`, dentro de la rama `real_movement` que
crea una transferencia. Después de establecer tipo, ID, usuario, fecha, importe,
cuentas origen/destino y enlaces finales, `with_history_keys` copia el documento
para insertarlo junto con sus claves privadas en el mismo `insert_one` y sesión
existentes. No hay una segunda escritura de claves ni transacciones anidadas.

El control `MONEYFLOW_HISTORY_KEYS_WRITE_ENABLED` permanece desactivado por
defecto. Configuración y .env no se modifican. Las lecturas indexadas y R4
continúan sin activar. Este bloque no instrumenta Recurrencias ni el núcleo R4.

Una aportación administrativa no crea transferencia ni llama al generador,
aunque el control esté habilitado en pruebas. Aportes, metas, recibos y journals
no reciben `_history_keys`. El control desactivado conserva la inserción anterior.

## Garantías conservadas

- Depósito: cuenta indicada por el aporte → cuenta vinculada a la meta.
- Retiro: cuenta de la meta → cuenta indicada por el aporte.
- Recomputación original de ambos saldos y seguimiento de la meta sin cambios.
- IDs deterministas y fingerprint del payload original intactos, incluso cuando
  la fecha se omite. Un reintento no recalcula un movimiento confirmado.
- Conflictos de payload siguen rechazándose con 409.
- Todos los cambios permanecen dentro de `payment_transaction`, sin modificar
  su implementación ni el tratamiento de errores o commits inciertos.
- Eliminar una meta conserva las transferencias y sus saldos y retira enlaces.
  Las claves no cambian porque esos enlaces no son fuentes de derivación.
  El recibo retirado conserva la protección ante reintentos tardíos.
- El saneamiento público existente oculta `_history*`; no se cambian contratos.

## Pruebas realizadas

Antes de instrumentar: 13 pruebas nuevas en memoria, con 6 fallos por ausencia
de claves. Después de instrumentar: 13/13 aprobadas.

MongoDB: 14/14 pruebas aprobadas en una única base nueva, sintética y conservada:
`test_c3_goal_keys_7c25efa9879348e6bbc1e08f5743f913`.
El arnés verifica URI local, PRIMARY, replica set, sesiones y ausencia del nombre
antes de crearla. Cada escenario utiliza sus propias colecciones dentro de esa
base. El auditor restringe comandos de datos a la nueva base, permite únicamente
comandos administrativos necesarios y confirma ausencia de drop e índices
explícitos. No utiliza bases financieras ni experimentales anteriores.

Cobertura: depósitos y retiros reales; origen/destino y saldos; aportes
administrativos; control desactivado; fecha omitida; reintento idéntico y payload
incompatible; aportaciones independientes iguales; concurrencia con misma
intención; rollback tras el primer saldo y tras recibo/recomputación de meta;
ready/unverifiable; eliminación conservando transferencia y claves; validaciones
de cuentas y retiros sin escrituras.

La prueba MongoDB de dos retiros concurrentes de $70 tras un depósito de $100
establece snapshots concurrentes y comprueba revalidación: uno se acepta, el otro
se rechaza con 422; ahorro final $30, saldos $970/$1030 y dos transferencias
verificables (depósito y retiro). También se inyecta pérdida de confirmación
DESPUÉS de un commit real, recuperando la misma intención sin duplicar dinero.
No equivale a una interrupción física de red ni a un failpoint del servidor.

## Límites

Las fechas se normalizan según el contrato existente antes de insertar. La
prueba `unverifiable` inyecta solamente un fallo de verificación del parser
derivado, sin cambiar fecha o importe financieros; no afirma que el endpoint
acepte fechas inválidas. No se migra ni repara historial.

No se probó Samsung en este bloque. No se garantiza cobertura global para una
lectura indexada futura: otros escritores y provisionamiento requieren etapas y
autorizaciones separadas. La desactivación del control no recalcula metadatos
históricos; las lecturas indexadas permanecen desactivadas.
