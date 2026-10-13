# C3 — Claves privadas en pagos recurrentes heredados

## Alcance

`create_recurring_record` (`POST /api/recurring-payments/{rid}/payments`)
incorpora `_history_keys` exclusivamente cuando `mode=expense` crea un gasto.
Después de fijar ID, usuario, fecha normalizada, importe, cuenta, categoría y
vínculos finales, `with_history_keys` copia el movimiento para insertarlo junto
con las claves en el mismo `insert_one` y sesión de `payment_transaction`.
No hay escrituras posteriores de claves ni transacciones anidadas.

La configuración no cambia: `MONEYFLOW_HISTORY_KEYS_WRITE_ENABLED` permanece
desactivado por defecto; lecturas indexadas y R4 permanecen sin activar. El
selector R4 sigue anterior a la rama heredada y su núcleo no se instrumenta.

## Modalidades y compatibilidad

- `expense`: genera claves únicamente con el control habilitado. El control
  desactivado no llama al generador y conserva la inserción anterior.
- `link`: conserva el movimiento, sus fuentes y claves existentes. Su escritura
  administrativa de enlaces no regenera claves ni rellena historial sin claves.
  Retirar seguimiento elimina solo los enlaces y conserva gasto, saldo y claves.
- `mark`: no crea movimiento ni genera/actualiza claves. Las reglas heredadas de
  seguimiento, `settles`, importe variable y sobrepago autorizado no cambian.

Los recibos recurrentes no reciben claves. IDs, fingerprints del payload
original, fechas/vencimientos, estados y controles referenciales se conservan.
Un reintento idéntico devuelve el recibo original; payload diferente produce 409.
Un recibo retirado conserva el rechazo a reintentos tardíos (sin nuevo movimiento).

`delete_recurring_record` no cambia: eliminar un gasto expense conserva la
protección frente a plantillas, borra su movimiento y devuelve dinero una vez.
Retirar link conserva el gasto financiero. Las actualizaciones administrativas
no invalidan claves porque no cambian las fuentes del contrato.
El saneamiento público existente sigue excluyendo `_history*`.

## Evidencia ejecutada

Antes de integrar: 13 pruebas nuevas en memoria, 4 fallos por claves ausentes.
Después: 13/13 aprobadas.

MongoDB: 16/16 pruebas aprobadas en una única base nueva sintética y conservada:
`test_c3_recurring_keys_4d1804474be84c46b1d040570d9021d8`.
El arnés verifica URI local, PRIMARY, replica set, sesiones y ausencia previa
del nombre antes de crearla. Aísla colecciones por escenario y audita comandos
para restringir datos a esa base. No crea índices explícitos, no limpia bases y
no consulta bases financieras ni experimentales anteriores.

Pruebas: expense, link con y sin claves, mark y retiro, control desactivado,
fecha omitida, misma intención y payload incompatible, pagos iguales legítimos,
otros períodos, creación concurrente con misma clave, eliminación/devolución
única, tombstone/reintento tardío, rollback después del saldo (creación y
eliminación), protección de plantillas, ready/unverifiable y respuestas públicas.

El conflicto real entre dos gastos de $70 sobre el período de $100, desde
cuentas distintas, produjo 200 y 422, un solo gasto y saldo conjunto $1930.
Los intentos de coordinación fueron [1, 3], con relectura tras conflicto MongoDB.
También se verificaron eliminaciones concurrentes sin segunda devolución.

La pérdida de confirmación se inyectó en el cliente después de un commit real,
tanto al crear como al eliminar; el reintento original no duplicó dinero. No se
simuló una caída física de red ni un failpoint del servidor.

## Limitaciones

Las fechas siguen normalizándose conforme al endpoint existente. La prueba de
`unverifiable` inyecta solo una incapacidad de verificación del parser derivado:
no cambia la fuente financiera ni afirma aceptación de fechas inválidas.
No se reparan ni migran fechas o claves históricas.

No hubo prueba física Samsung ni activación. El mantenimiento en el núcleo R4
y las condiciones para lecturas indexadas requieren etapas separadas. No se
asume cobertura completa del historial ni se regeneran claves al desactivar el
control. No se modifica el sistema de plantillas recurrentes.
