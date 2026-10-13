# R4 — obligaciones compartidas e integración controlada

## Estado actual y alcance

`backend/shared_obligations.py` es un módulo interno independiente. No abre un
cliente MongoDB, no carga dotenv, no define rutas, no ejecuta tareas de arranque
y es utilizado por los guards y adaptadores transaccionales del servidor.
Las etapas 2D.1 a 2D.7 y las correcciones de cierre están implementadas: lecturas,
pagos compartidos, anulaciones, seguimiento administrativo, edición coordinada,
journal persistente del cliente y conciliación verificable. R4 permanece
**desactivado por defecto**; completar la implementación no autoriza activarlo.
Las operaciones sin historial R4 conservan el flujo heredado. Las obligaciones
reservadas o gestionadas no pueden volver silenciosamente a ese flujo.

Las funciones de escritura son explícitas y usan la transacción del llamador;
`install_indexes` es exclusivamente administrativo. Las pruebas se limitan a
dobles de memoria y bases nuevas sintéticas. No existe migración, activación
automática ni creación de índices sobre entornos habituales o Emergent.

Las secciones siguientes conservan la secuencia histórica de implementación.
Sus límites de etapa no representan integraciones pendientes actuales. Siguen
pendientes la activación administrativa autorizada, la prueba física de R4 en
Samsung y las mediciones de rendimiento con historiales representativos.

## Identidad y esquema versión 1

Una sola colección `shared_obligations` conserva un documento por obligación y
vencimiento, sin listas crecientes de pagos. Se usa una colección independiente
porque la identidad debe poder sobrevivir a retirar el seguimiento; no es un
movimiento financiero ni un nuevo saldo almacenado.

Campos:

| Campo | Invariante |
|---|---|
| `_id` | UUID v5 determinista de versión, environment_id, user_id, recurring_id y original_due_date |
| `version` | Entero 1; una versión desconocida no se adopta |
| `revision` | Entero no negativo, inicialmente 0; utilizado para coordinación transaccional |
| `environment_id`, `user_id`, `mode` | Contexto financiero verificado; modo `single_user` |
| `bill_id`, `recurring_id` | Asociación 1:1 de factura con ese vencimiento |
| `original_due_date` | Fecha ISO literal e inmutable del vencimiento |
| `actual_amount` | Importe real de la factura, Decimal128, positivo y finito |
| `estimated_amount` | Estimación recurrente original, separada del importe real |
| `variable_snapshot` | Indicador variable de la configuración al establecer el vínculo |
| `schedule_snapshot` | Versión original: frequency, start_date, due_day, valid_from, amount |
| `lifecycle` | `bound`, `tracking_detached` o `archived`; no es el estado financiero |
| `created_at` | Fecha ISO con zona horaria |

Los IDs no dependen de la URI, IP o reinicios. El entorno procede exclusivamente
de `financial_context.get_financial_context`, con el identificador esperado
verificado contra `moneyflow_metadata/financial-context`. No se genera ni cambia
ese UUID. `effective_user` debe ser la identidad efectiva del servidor, actualmente
`default-user`; no es una cabecera ni una prueba de autenticación. `Scope` es un
valor interno para funciones puras, no una credencial.

Una clonación con cambio de contexto no reasigna identidades anteriores. Las
consultas por factura detectan un environment_id antiguo y rechazan la adopción.
El modo single_user no introduce autenticación ni separación multiusuario nueva.

## Resolución conservadora

`resolve_documents` prepara o verifica un documento sin escribir. Recibe la
función `_rp_occurrences` existente del servidor; no copia sus reglas de fechas
ni importa el arranque de la aplicación.

Para asociaciones nuevas se exige un vencimiento **exacto**, sin elegir la fecha
más cercana. `once` puede representar un único vencimiento de la recurrencia;
las series requieren frecuencias equivalentes (yearly/annual, por ejemplo).
Los importes fijos deben coincidir. Para recurrencias variables pueden diferir
importe real y estimación. Estas reglas se aplican a la rama compartida integrada;
los casos con desplazamientos de fecha u otras políticas de compatibilidad
requieren revisión explícita antes de autorizar su activación.

Se detectan candidatos múltiples, padres ausentes, usuarios/contextos diferentes,
versiones de calendario ambiguas y metadatos inválidos. `series_id` no se trata
como referencia obligatoria a una factura existente.

Una identidad persistida se verifica con su snapshot original: cambiar fechas o
programación no mueve el vencimiento histórico. Un cambio de importe real exige
la actualización explícita y coordinada de la etapa 2D.6; el resolver no lo copia
ni normaliza automáticamente. No se autoriza retargeting ni liberación automática
de una asociación. Las retiradas coordinadas se describen en la etapa 2D.4.

`resolve_shared_obligation` solo lee un snapshot. Puede devolver un borrador con
`persisted=False`; eso no demuestra que un pago pueda enviarse ni activa nada.
`create_shared_obligation` exige índices y una transacción existente, rechaza
cualquier historial previo del período y movimientos recurrentes huérfanos.
No migra ni siquiera un historial aparentemente verificable. Coordina los padres
mediante `_reference_revision`, inserta solo la identidad y deja escapar los
conflictos al manejador existente para reintentar la transacción completa.
Releer una identidad ya creada no incrementa revisiones ni la sustituye.

## Verificación financiera de solo lectura

`verify_payments` y `inspect_payments` verifican identificadores, enlaces inversos,
período, usuario, tipo expense, importe finito exacto y cuenta. La inspección
MongoDB también comprueba la existencia de las cuentas de los movimientos vivos.
Los importes no se redondean para ocultar discrepancias históricas.
El contexto Decimal de la suma se ajusta localmente para conservar importes
verificables de mayor precisión, sin cambiar el contexto global de la aplicación.
Un importe no representable exactamente en Decimal128 se rechaza; no se redondea
para introducirlo en la identidad. También se verifican categorías y recibos
inversos adicionales, incluidos los que pertenecen a otra factura o período.

Un gasto con un recibo de factura y un registro recurrente se cuenta una vez por
su `transaction_id`. Dos gastos de 30 con IDs distintos suman 60, aunque monto,
fecha o descripción coincidan. Vínculos incompletos, documentos repetidos,
movimientos extra o importes por encima de la obligación requieren conciliación.

Para una obligación real de 50 y una estimación variable de 100, un gasto
verificado de 50 produce pagado 50 y pendiente 0. No altera la estimación futura
ni las fórmulas actuales de la aplicación; es un resultado del nuevo módulo.

El estado financiero se deriva de evidencia, no de `lifecycle` ni de `deleted`:

- Un grafo histórico activo completo de factura/registro/movimiento es verificable
  por sus IDs, sin añadir campos ni adoptarlo automáticamente.
- Una marca sin movimiento es seguimiento, no dinero pagado. Se devuelve como
  `tracking_only_records` y `requires_reconciliation=True`; no autoriza un nuevo
  gasto automático.
- Un `deleted: true` heredado es ambiguo: puede significar anulación o retirada
  de seguimiento. No se presume devolución ni se reabre el pendiente.
- Los recibos compartidos utilizan `_shared_obligation_id`,
  `_shared_origin_receipt_id` y `_shared_financial_state` (active/annulled).
  La procedencia debe identificar un recibo original realmente presente,
  coincidir con ambos documentos y con el movimiento cuando existe.
- Retirar seguimiento con procedencia explícita y conservar el gasto mantiene
  el importe pagado. Anular exige el marcador explícito y ausencia del movimiento
  y de vínculos inversos vivos. Un recibo corrupto no se transforma en importe 0.
  Esto incluye retirar solo una vista: el recibo complementario retirado debe
  identificarse inequívocamente por su origen financiero y su movimiento, sin
  reparar los enlaces públicos eliminados. No se permite esa excepción para
  vínculos activos incompletos ni para tombstones heredados sin procedencia.
- Un pago compartido originado como expense desde Recurrencias necesita esa
  procedencia explícita para su recibo complementario de factura. No se acepta
  una combinación heredada incoherente por adivinar su origen.

Estos campos internos son utilizados por los adaptadores compartidos de las
etapas 2D.3 a 2D.5. Su exclusión recursiva y los serializadores públicos impiden
exponerlos; la colección de identidades no se publica.

### Protecciones de la revisión focalizada

La retirada de seguimiento permite enlaces públicos ausentes, pero nunca enlaces
conservados contradictorios. Se comprueban los IDs de factura, recurrencia, pago,
registro y sus referencias inversas, también cuando los recibos están retirados.
La procedencia interna no sustituye estas comprobaciones. Las discrepancias
producen HTTP 409 en el módulo, sin escrituras.

`inspect_payments` relee la identidad canónica en la misma sesión/transacción.
Compara IDs, versión y revisión; una revisión obsoleta se rechaza con HTTP 409.
Los importes y estados se toman del documento persistido, aunque el llamador
proporcione una copia alterada con la misma revisión. Un borrador exige
`draft=True` explícito y solo se admite cuando no existe ninguna identidad por
ID, factura o período; no puede sustituir ni reasignar una identidad persistida.
Las funciones puras continúan disponibles para verificar borradores sin MongoDB.

La inspección también examina los movimientos que conservan la referencia a la
recurrencia. Para excluir uno debe demostrar otro período mediante un recibo
inverso único, fecha de vencimiento literal y vínculos/importe/cuenta verificables.
Los movimientos con metadatos compartidos de otro período requieren además su
identidad persistida y la verificación del grafo financiero. Un grafo histórico
completo factura/pago/registro/movimiento sin esos metadatos también puede
demostrar otro período: se verifica la factura existente, su usuario y recurrencia,
un único pago y registro por movimiento, todos los enlaces directos/inversos,
cuenta, categoría del registro y el importe decimal exacto. No se crea ni adopta
una identidad para excluirlo. El vencimiento almacenado del registro es la
referencia histórica; editar la fecha actual de la factura no reasigna el pago.
Los recibos heredados retirados sin procedencia financiera explícita siguen
siendo ambiguos y se rechazan. Las retiradas con procedencia compartida se
verifican mediante el camino existente. No se usa la fecha del gasto,
importe o descripción para atribuir un período. Se conserva un período histórico
válido aunque la programación actual haya cambiado. Un movimiento huérfano o
ambiguo bloquea la inspección con HTTP 409; no se cuenta ni se repara.

Esta política es conservadora: una incoherencia no conciliada en otro movimiento
de la misma recurrencia puede impedir inspeccionar el período solicitado. No
autoriza borrados ni descuentos. Las lecturas y escrituras compartidas rechazan
historial ambiguo; las obligaciones sin gestión R4 conservan el flujo heredado.
La coordinación y la conciliación están integradas en las etapas posteriores,
sin activar el interruptor.

## Índices y activación futura

### Etapa 2A: preparación de activación (alcance histórico)

`backend/config.py` incorpora `MONEYFLOW_SHARED_OBLIGATIONS_ENABLED`, con valores
exactos `0` o `1` y valor ausente equivalente a `0`. `Settings` conserva sus campos
anteriores y añade `shared_obligations_enabled=False`. Un valor mal formado se
rechaza como configuración inválida. No se cambió ningún archivo `.env` ni se
habilitó R4. El interruptor por sí solo no activa rutas ni autoriza escrituras.

`require_activation` es una función interna explícita utilizada por los
adaptadores compartidos de `server.py`, nunca como tarea de arranque. Exige el interruptor habilitado, una sesión con
transacción activa, una topología replica set o mongos con sesiones y versión
compatible, y PRIMARY disponible. Reutiliza `get_financial_context` de R6 y el
único pin `MONEYFLOW_EXPECTED_ENVIRONMENT_ID`: comprueba los metadatos mediante
una lectura real dentro de la transacción. Comprueba también ambos índices con
`require_indexes`; no instala ni repara requisitos. Los errores de conexión o
requisitos no verificables producen HTTP 503 interno, sin alternativa parcial.
Estas comprobaciones no garantizan disponibilidad futura ni confirmación del
commit: las operaciones compartidas permanecen en el manejador transaccional actual.

`has_managed_obligation` detecta identidades persistidas por factura o pareja
recurrencia/vencimiento y marcadores conservados en padres, recibos o movimientos
consultables por sus IDs. No depende del interruptor ni de tener un pin disponible
para detectar un contexto anterior. Un documento de identidad de versión o
contexto desconocidos cuenta conservadoramente como gestión R4. Lo mismo sucede
con marcadores corruptos o recibos retirados; no se borran, migran ni normalizan.
Los errores de lectura generan HTTP 503, nunca se interpretan como ausencia.
La identidad efectiva del usuario siempre debe ser proporcionada por el servidor.

`require_legacy_allowed` rechaza con HTTP 409 una obligación gestionada. En la
etapa 2B ya se conecta a las rutas de escritura descritas abajo, incluso con el
interruptor apagado. No habilita una alternativa compartida: si hay gestión
previa, la escritura antigua se bloquea. Si se perdieran la identidad y todos
sus marcadores, el detector no puede reconstruir ese origen: no se inventa.

Procedimiento futuro, no ejecutado en bases persistentes:

1. Revisar la integración financiera y las lecturas ya implementadas, y conservar
   los guards de desactivación de la etapa 2B al autorizar la activación.
2. Verificar el destino exacto y el contexto R6 esperado del entorno elegido.
3. Revisar historial/ambigüedades y autorizar por separado los índices requeridos.
4. Crear índices únicamente mediante el procedimiento administrativo autorizado;
   nunca durante startup, imports o comprobaciones de preparación.
5. Configurar explícitamente el interruptor en el entorno autorizado y verificar
   `require_activation` con una lectura transaccional antes de permitir pagos.
6. No copiar UUID, configuración local ni activación a Emergent. Cada despliegue
   requiere contexto y autorización propios. No hay activación por nombre de
   base, IP, URL ni valor predeterminado.

Las pruebas usan flags habilitados solamente en objetos de configuración
sintéticos y comprueban snapshots financieros intactos. La falta de transacciones
se prueba mediante topologías/respuestas simuladas; la compatibilidad real se
comprueba en el replica set local, exclusivamente en bases nuevas de pruebas.
No se inicia ningún servicio standalone para estas pruebas.

Se definen dos índices únicos, sin filtro parcial ni TTL:

1. `(user_id, recurring_id, original_due_date)`: un propietario por vencimiento.
2. `(user_id, bill_id)`: una identidad por factura.

El índice nativo `_id` protege además la identidad determinista. Archivar no
libera las claves históricas; así no se recrea la identidad para evadir un pago.
Los índices no incluyen environment_id deliberadamente: reprovisionar el contexto
de la misma base no permite duplicar silenciosamente una asociación.

`require_indexes` verifica nombre, claves, unicidad y ausencia de filtros/sparse
antes de escribir. Si faltan requisitos, devuelve HTTP 503 dentro del módulo;
no instala nada. `install_indexes` es una llamada administrativa explícita y no
debe ejecutarse en una base existente sin autorización y revisión de destino.

Las políticas conservadoras aprobadas están implementadas en las etapas 2D.3 a
2D.7: pendiente común, recibos, revisiones, anulaciones, siguiente período,
lecturas, serializadores y recuperación. No se adopta historial automáticamente.
Cualquier nueva política de asociación histórica exige autorización separada.
No se cambia el manejador transaccional ni se activa R6 en Emergent.

## Pruebas

### Etapa 2C: preparación del núcleo transaccional (alcance histórico)

`register_shared_payment` recibe el ID de obligación persistida, origen bill o
recurring, IDs originales de recibo/movimiento y el payload original model_dump.
La identidad se relee en cada intento; no se utiliza una copia antigua de revisión.
Se incrementa efectivamente revision dentro de la sesión existente y se verifica
el pendiente común por movimientos únicos. Los padres y la cuenta se coordinan
mediante el mecanismo R3 existente, evitando pérdidas de saldo entre obligaciones.
Un exceso del pendiente, incluso allow_overpay, produce HTTP 409 y aborta todas
las escrituras. No se suma dos veces un gasto por tener dos recibos.

Un pago crea un único gasto y dos recibos financieros complementarios. El ID
original del origen y del movimiento no se cambian; para origen bill se conserva
el esquema bill-rp-record existente. El recibo de factura complementario de un
origen recurring usa UUID v5 de shared-bill-payment:<recibo original>. Los slots
de ID se comprueban contra documentos anteriores, incluido su id lógico.
Se preserva request_fingerprint del origen con el algoritmo actual y se conserva
una cápsula interna _shared_intent con origen, IDs, payload y huella exactos.
Cambiar datos o IDs del reintento produce conflicto. Dos intenciones diferentes
del mismo importe son dos pagos legítimos mientras haya pendiente suficiente.

El resultado interno SharedPaymentResult distingue created, financial_state y
los recibos originales/complementarios. Un resultado del callback todavía no es
confirmación de commit: los adaptadores esperan payment_transaction.
El núcleo no abre sesiones, no hace commits ni implementa otro manejador/retry.
Un commit incierto conserva HTTP 503 del manejador actual; recuperar con el mismo
origen, IDs y payload relee el evento confirmado sin insertar ni recalcular otra vez.
Un recibo complementario ausente o un historial sin cápsulas R4 no se adopta.

`change_shared_payment` soporta annul, retire_bill, retire_recurring y retire_both.
Anular elimina una sola vez el gasto, recalcula mediante la función existente y
mantiene ambos recibos anulados para impedir resurrección de la intención.
Retirar seguimiento solo conserva el dinero y su procedencia, retirando enlaces
públicos coherentemente. Retirar ambas vistas deja lifecycle tracking_detached y
bloquea nuevas intenciones hasta una acción futura explícita de restablecimiento.
No se libera la unicidad histórica. El período sigue siendo original_due_date
aunque cambien después la fecha de factura o la programación recurrente.

El recálculo de saldo se pasa como callback existente; no se copia su fórmula ni
se altera su fórmula al integrar los adaptadores en server.py. Los movimientos usan el formato numérico nativo actual;
si convertir un importe a float cambia su valor decimal, se rechaza en vez de
redondearlo silenciosamente. El pendiente se calcula con Decimal exacto. La
estimación variable original queda separada; una obligación real de 50 puede
quedar pagada con 50 aunque su estimación sea 100.

Límites del núcleo y evolución de la integración:

- Este núcleo registra pagos expense nuevos. La etapa 2D.5 integra link/mark
  mediante intenciones administrativas separadas; no adopta historial ambiguo.
- Los adaptadores llaman require_activation, preservan el payload del modelo
  y los IDs existentes, y suministran el recálculo correspondiente al usuario
  efectivo. No se habilitó ningún flag ni se implementó autenticación nueva.
- La recuperación requiere el mismo origen, IDs y payload. Si un cliente inventa
  IDs nuevos tras perder una respuesta, el núcleo los considera otra intención:
  no deduplica importes. La estrategia de claves/persistencia para los clientes de
  Facturas y Recurrencias está implementada mediante el journal de la etapa 2D.7.
- effective_date permite pasar la fecha normalizada con el mecanismo existente,
  sin cambiar el payload/huella original. Debe conservarse entre reintentos y
  corresponder al instante original si el cliente envió una fecha explícita.
- Las etapas 2D.1 a 2D.6 integran generación del siguiente período, lecturas,
  serializadores y edición conservadora de padres. Las eliminaciones inseguras
  de padres reservados o necesarios para el historial permanecen bloqueadas.
- Los parents deben existir y conservar el vínculo y el importe real; no se
  autoriza una edición descoordinada ni una reasignación histórica.
- Los guards 2B bloquean el retorno al flujo antiguo. Las etapas 2D.3 y 2D.4
  conectan el núcleo a las rutas públicas bajo activación verificada. Sus funciones
  internas no son un procedimiento administrativo para bases habituales.

```bash
python3 -B -m unittest backend.tests.test_shared_payments
MONEYFLOW_R4_CORE_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_shared_payments_mongodb
```

Las pruebas reales crean exclusivamente test_r4_core_<uuid>, verifican vacío,
127.0.0.1:27018, replica set y sesiones antes de escribir. Los índices se instalan
explícitamente solo en ese fixture nuevo, nunca durante ejecución del núcleo.
Se auditan los comandos y se conservan las bases. Se comprueban saldos, recibos,
movimientos, revisiones, ambos orígenes, parciales iguales, conflictos 112,
rollback por escritura y commit incierto con recuperación sin duplicación.

### Etapa 2B: protección de escrituras antiguas

Se comprueban, dentro de las transacciones existentes, POST/PUT/DELETE de
Facturas y Recurrencias, registro y eliminación de pagos, retirada de registros,
pause/resume/end y los movimientos genéricos PUT/DELETE. La creación de una
factura vinculada no puede reclamar un período R4; tampoco se permite recrear un
padre reservado mediante la misma clave o vincular un gasto gestionado como nuevo
origen. Se examinan referencias inversas incluso en recibos retirados. La ausencia
de marcadores en el movimiento no oculta una identidad conservada por su recibo.

Las operaciones globales sobre una recurrencia comprueban todos sus períodos.
Un pago de un período independiente puede seguir usando la ruta antigua si no
tiene gestión R4. Un gasto R4 huérfano cuyo período no pueda probarse bloquea la
operación; uno de otro período solo se excluye con contexto y grafo verificables.
Los guards no escriben documentos ni dependen de habilitar el interruptor.

`_rp_set_state` conserva su máquina de estados, validaciones, campos y respuesta,
pero ejecuta guard, lectura, actualización y respuesta dentro de una única
`payment_transaction`. No se modificó ese manejador ni se añadieron transacciones
anidadas. Un MongoDB sin soporte transaccional devuelve HTTP 503 sin cambios.
Un commit incierto conserva HTTP 503 y puede haber confirmado el cambio de estado;
debe consultarse el estado antes de reintentar. No se añadió una clave de
idempotencia para pause/resume/end ni se repite automáticamente un commit incierto.
Los conflictos entre pausa y una reserva coordinada se reintentan leyendo el
estado nuevo; las pruebas cubren ambos órdenes de commit y rollback intermedio.

La etapa 2B preparó únicamente los bloqueos. Las etapas 2D.1 a 2D.7 ya integran
pagos, anulaciones/retiradas, lecturas y serializadores. Con el interruptor apagado
las obligaciones gestionadas siguen bloqueadas para escrituras heredadas.
Antes de desplegar debe verificarse permiso de lectura sobre shared_obligations;
un permiso denegado o error de consulta bloquea, nunca habilita una alternativa.
No se configura ni comprueba Emergent desde estas pruebas.

```bash
python3 -B -m unittest backend.tests.test_shared_guards
MONEYFLOW_R4_GUARD_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_shared_guards_mongodb
```

Estas pruebas generan bases nuevas `test_r4_guards_<uuid>`, validan destino,
replica set, PRIMARY y vacío previo, y auditan todos los comandos. No ejecutan
createIndexes/dropIndexes ni limpian bases. Las reservas/metadatos de carreras son
fixtures sintéticos explícitos que coordinan padres, no activación del backend.
Los dobles existentes de pruebas se adaptaron para representar in_transaction y
cargar los guards/rutas desde AST, conservando las restricciones de aislamiento.

Las suites reales de etapas 1/2A que crean índices no se ejecutan durante esta
fase histórica de guards con prohibición de índices; las suites posteriores
pueden crear índices exclusivamente en sus propias bases sintéticas nuevas.

```bash
python3 -B -m unittest backend.tests.test_shared_obligations
MONEYFLOW_R4_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_shared_obligations_mongodb
```

Cada prueba real genera `test_r4_stage1_<uuid>`, verifica vacío antes de escribir,
127.0.0.1:27018, replica set app_finanzas_dev_rs, PRIMARY y sesiones. Audita todos
los comandos: solo su propia base y admin. Las bases se conservan; no se consultan
ni limpian las anteriores. La prueba de ausencia de índice retira únicamente un
índice creado en su propia base nueva, nunca de una base existente.

Se cubren identidad estable, contexto/reinicio, unicidad, conflicto real de
creación, rollback, commit incierto, períodos congelados, referencias ambiguas,
recibos/ledger, dos parciales iguales, retirada y anulación, índices y serialización.
Las pruebas puras compartidas se ejecutan también en la suite real; se distinguen
de las pruebas que persisten e inspeccionan gráficos financieros en MongoDB.
Una prueba explícita confirma que las operaciones antiguas sin gestión R4 mantienen
el resultado anterior (incluido el defecto conocido), y que una reserva R4 bloquea
escrituras posteriores. Esa prueba aislada de guards no sustituye las pruebas
de integración financiera de las etapas 2D.3 a 2D.7.
La regresión del falso positivo crea el pago de noviembre mediante el endpoint
actual y demuestra que inspeccionar octubre no lo cuenta, no bloquea ni modifica
documentos. Se prueban además enlaces cruzados, cuentas/importes incompatibles,
recibos ambiguos, fechas históricas frente a fechas actuales, dos parciales y
reintento con la misma clave, conservando la detección de huérfanos.

## Etapa 2D.1: lecturas preparadas, flujo financiero desactivado

La etapa 2D.1 preparó las lecturas sin conectar entonces `register_shared_payment`
ni `change_shared_payment`; las etapas 2D.3 y 2D.4 completaron esa conexión.
No se activa `MONEYFLOW_SHARED_OBLIGATIONS_ENABLED`. No provisiona
contextos, índices ni identidades. Los cálculos públicos antiguos siguen activos;
solo se aplica filtrado de metadatos internos a las respuestas afectadas.

### Adaptadores internos

- `read_shared_view`: selecciona por factura **o** recurrencia y vencimiento
  original, dentro de una transacción snapshot proporcionada por el llamador.
  Devuelve `None` únicamente tras comprobar ausencia de identidad e historial
  R4. Identidad duplicada, procedencia perdida o historial incoherente producen
  409. Los errores MongoDB producen 503; nunca habilitan un cálculo alternativo.
  Una identidad existente exige contexto R6 verificado. No adopta borradores.
- `read_shared_periods`: enumera vencimientos originales persistidos, incluso
  cuando ya no aparecen en la programación actual. No usa fechas próximas.
- `shared_bill_public` y `shared_recurring_public`: conservan las formas públicas
  y proyectan pagado/pendiente usando `inspect_payments`. El importe real de la
  obligación manda sobre el estimado: previsto 100 y factura real 50 significa
  pendiente 50 antes de pagar. No se reduce ningún importe almacenado.
- `shared_period_states`: prepara estados por período para resúmenes, ocurrencias
  y recordatorios. Incluye períodos históricos sin reconstruirlos por importe.
- `shared_paid_events`: entrega movimientos financieros únicos verificados para
  totales mensuales y calendario; la fecha efectiva viene del movimiento.
- `shared_calendar_due`: proyecta un evento planificado sobre el vencimiento
  original y pendiente común. Devuelve `None` cuando ya no queda dinero pendiente.
  La integración de la etapa 2D.2 suprime el evento recurrente duplicado mediante
  los IDs de factura/recurrencia y período de la identidad, nunca por proximidad.
- `_shared_bill_read` y `_shared_recurring_read`, en `server.py`, preparan las
  proyecciones por documento/período, conectadas a las rutas públicas en 2D.2.

Una marca sin movimiento, aunque tenga `settles=True`, no paga dinero. Retirar
recibos de seguimiento puede ocultarlos de las listas visibles, pero conserva el
importe pagado cuando sigue existiendo el movimiento real verificable. Anular
financieramente elimina ese movimiento mediante el núcleo existente y deja sus
recibos históricos; el lector no los vuelve a contar. El lector nunca anula,
retira ni modifica ningún documento.

### Serialización y consumidores preparados en 2D.1

`public_financial_document` crea copias recursivas sin `_shared_*`,
`request_fingerprint`, `idempotency_key`, `_id`, `_payment_revision` ni
`_reference_revision`. Conserva IDs públicos, enlaces, null y cadenas vacías.
Se aplica a respuestas de Facturas/Recurrencias, incluidas recuperaciones por
idempotencia, y al listado de movimientos. El filtrado no altera el journal
almacenado, fingerprints ni cálculos financieros. Los calendarios actuales
construyen eventos mediante campos públicos explícitos.

La etapa 2D.2 conecta la snapshot a los consumidores preparados en esta tabla:

| Consumidor existente | Lectura preparada / integración posterior |
| --- | --- |
| `list_bills`, `get_bill`, `bills_summary` | Proyección de factura, pagado común y eventos reales para `paid_month`; conservar enriquecimiento de cuentas y filtros actuales. |
| `recurring_overview` | Estados compartidos antes de calcular tarjetas, totales y recordatorios. |
| `get_recurring_payment` | Total/count financiero por movimientos únicos; combinar períodos normales sin reinterpretar su contrato actual. |
| `recurring_occurrences`, `_rp_month_states`, `_rp_next_due` | Incorporar períodos originales y usar sus estados verificados. La programación futura permanece separada del historial pagado. |
| `recurring_link_candidates` | Selección de candidatos, no evidencia de pago común; la revisión de cierre verifica y sanea los candidatos R4 restaurables. |
| `_cal_events`, `calendar_events`, `calendar_summary`, `calendar_upcoming` | Pendiente común y supresión del seguimiento duplicado por identidad; movimientos reales una sola vez. |

Estas conexiones quedaron implementadas en 2D.2. No se mezclan lecturas no
transaccionales con una snapshot financiera. Las etapas 2D.3 a 2D.6 implementan
link limitado, mark administrativo, cambios conservadores de padres y generación
del siguiente período; su activación sigue requiriendo autorización explícita.

### Verificación aislada

```bash
python3 -B -m unittest backend.tests.test_shared_reads
MONEYFLOW_R4_READ_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_shared_reads_mongodb
```

La suite MongoDB reutiliza el fixture auditado que crea una base
`test_r4_core_<UUID>` nueva por caso, comprueba destino loopback 27018 y replica
set antes de escribir y audita los comandos. Los datos son sintéticos, los índices
solo se preparan en esas bases nuevas y todas ellas se conservan. No se consultan
ni limpian bases existentes. Los snapshots antes/después comprueban que las
lecturas no cambien balances, movimientos, recibos ni metadatos.

## Etapa 2D.2: conexión pública de lecturas, sin activar pagos

Esta etapa reemplaza la condición de desconexión de lectores descrita en 2D.1.
El interruptor R4 sigue desactivado. En 2D.2 no se integraron escrituras;
las etapas 2D.3 a 2D.6 las conectaron después bajo activación verificada.
Las formas de respuesta permanecen iguales.

### GET conectados

- `/bills`, `/bills/summary`, `/bills/{bid}`.
- `/recurring-payments`, `/recurring-payments/overview`,
  `/recurring-payments/{rid}`, `/recurring-payments/{rid}/occurrences`.
- `/calendar/events`, `/calendar/summary`, `/calendar/upcoming`.

El listado simple de recurrencias conserva su importe configurado (estimado);
los estados por vencimiento muestran el importe real de la obligación compartida.
El detalle recurrente cuenta dinero y movimientos únicos para períodos R4,
conservando el comportamiento anterior para períodos normales. `mark` y
`settles` de un período compartido no liquidan dinero. Las marcas de períodos
normales conservan su semántica anterior mientras no exista gestión R4.

Los recordatorios, próximos vencimientos y paginación de ocurrencias incorporan
las fechas originales persistidas, incluso si desaparecen de la programación
actual. El calendario filtra las facturas sobre copias con su vencimiento original
(sin modificar documentos) y suprime el vencimiento recurrente duplicado mediante
la identidad exacta. Una marca nunca sustituye el gasto real de una obligación
compartida. El resumen mensual de Facturas usa las fechas e importes de los
movimientos únicos, incluyendo gastos cuyo seguimiento se retiró. Las facturas
pagadas no reaparecen como pendientes por retirar esos recibos.

### Instantánea, detección y aislamiento

`shared_read_route` usa probes de tamaño constante para detectar identidades y
los campos de procedencia conocidos en padres, recibos y movimientos. Un error
MongoDB devuelve 503; no significa ausencia. Sin historial, ejecuta las lecturas
anteriores y vuelve a comprobar ausencia antes de responder. Si R4 apareció
durante ellas, descarta el resultado y toma una snapshot. La ausencia verificable
no requiere iniciar transacciones ni disponer del contexto R6.

Con historial, se abre una transacción **solo de lectura**, con read concern
`snapshot`, sobre el mismo cliente existente. Se verifica el contexto esperado
R6 y se cargan por usuario las colecciones necesarias una sola vez. La inspección
por obligación y los lectores públicos reutilizan esa copia privada en memoria.
Un `ContextVar` mantiene el ámbito por petición y se restablece al finalizar,
incluso ante errores. Las siguientes rutas de escritura conservan su base real
y las protecciones anteriores; no usan esta snapshot.

Se verifican todas las identidades de la snapshot. Identidades duplicadas,
procedencia cruzada o perdida, padres incompatibles, fechas financieras no
verificables e historial ambiguo devuelven 409 antes de presentar importes.
Los gastos activos exigen una fecha ISO verificable para poder aparecer en
resúmenes/calendarios. Esta comprobación no modifica ni normaliza el histórico.
Los errores de lectura o de la transacción devuelven 503. No se introduce fallback
financiero ni se reutiliza/modifica el manejador de transacciones de pagos.

El filtrado recursivo de 2D.1 permanece en listas, detalles, estados, calendario y
respuestas de recuperación. La identidad y cápsulas completas solo existen en
objetos privados; no se exponen en la API.

### Rendimiento y límites

La prueba compara una y dos obligaciones gestionadas: el listado usa 13 lecturas
MongoDB en ambos casos (probe, carga de 11 colecciones y contexto). No hace
consultas de red por cada obligación. Los cursores de verificación posteriores
operan sobre la snapshot en memoria. Sin historial hay hasta 12 probes pequeños
adicionales para mantener el camino anterior sin exigir transacciones y detectar
la aparición concurrente de R4.

La cantidad de datos transferidos, la memoria y el trabajo de verificación crecen
con el historial del usuario. La carga incluye todo su historial financiero para
no ocultar recibos retirados, referencias inversas u otros períodos. No se limita
silenciosamente esa evidencia. Antes de activar escrituras en un entorno grande
se deberán medir carga y latencia con datos sintéticos de tamaño representativo;
una futura selección masiva más estrecha debe conservar las pruebas completas de
integridad. Esta etapa no agrega índices en ningún entorno persistente.

Un historial R4 corrupto puede bloquear las lecturas conectadas de ese usuario,
aunque el documento consultado sea normal: la carga compartida falla de forma
conservadora. No repara ni adopta automáticamente ese historial. La pérdida de
toda identidad y toda procedencia continúa siendo la limitación descrita en 2B.

### Estado posterior a 2D.2

- Expense, link limitado, mark, anulaciones y retiradas están integrados en 2D.3–2D.5.
- Generación coordinada y edición conservadora de padres están implementadas en 2D.3 y 2D.6.
- Recuperación persistente, conciliación e invalidación cruzada están implementadas en 2D.7 y la revisión de cierre.
- Siguen pendientes la activación administrativa explícita y los requisitos del entorno elegido.

`/recurring-payments/{rid}/link-candidates` sigue siendo selección de movimientos,
no una lectura de dinero pagado o pendiente. `/summary` sigue agregando cuentas,
movimientos reales y deudas; no suma recibos de Facturas/Recurrencias y conserva
sus cálculos. Ninguno necesita reinterpretar obligaciones para estas respuestas.
No se modificó frontend, configuración, Emergent ni datos existentes.

## Etapa 2D.3: POST financieros conectados, interruptor desactivado por defecto

Esta sección sustituye la condición de desconexión financiera de las etapas
anteriores. `pay_bill` y `create_recurring_record` llaman a un selector **dentro**
de su `payment_transaction`, antes del guard antiguo. No se modifica el manejador
transaccional, el cálculo de saldos ni las rutas de pagos de deudas.

### Selección exclusiva

- Interruptor ausente/desactivado: se mantiene el flujo anterior y su guard
  obligatorio. Una obligación gestionada/reservada por R4 devuelve 409; una
  obligación normal sigue funcionando como antes.
- Interruptor habilitado: una factura vinculada o un período recurrente con una
  única factura exacta utiliza el adaptador compartido. Se verifica contexto R6,
  entorno esperado, transacciones e índices antes de crear su identidad/pago.
  No hay fallback después de seleccionar R4.
- Un período independiente sin factura compartida conserva el flujo anterior,
  sujeto a sus guards. No se enlaza por proximidad ni coincidencia de importe.
- `expense` utiliza `register_shared_payment` exclusivamente: un movimiento,
  dos recibos verificables y un recálculo. No continúa las escrituras antiguas.
- La etapa 2D.5 incorpora mark administrativo y link limitado a restauración
  verificable de seguimiento R4. Los modos normales sin gestión compartida
  permanecen intactos; no se adopta un movimiento histórico ambiguo.
- Historial antiguo, ambiguo o identidades con programación indispensable ausente
  se rechazan. No se adoptan recibos ni se completan metadatos históricos.

Se mantienen los IDs originales por ruta y los fingerprints de `model_dump`.
El payload original permanece en la cápsula; fecha efectiva y vencimiento se
normalizan por separado conforme a los parsers existentes. Formatos de fecha
admitidos anteriormente (incluido el día compacto) no cambian el payload guardado.
Un replay con representación/payload diferente sigue rechazándose. Los importes
públicos inválidos y sobrepagos parciales devuelven 422; un período ya pagado y
conflictos de identidad/idempotencia devuelven 409. `settles` y `allow_overpay` no
cierran ni superan dinero pendiente compartido.

La respuesta conserva los campos de origen. Facturas mantiene `next_bill_id` en
la respuesta inicial y el formato anterior de replay; Recurrencias devuelve su
registro sin nuevos campos internos. Los recibos complementarios permanecen
almacenados para verificar el grafo y contar un movimiento una sola vez.

### Programación original y generación atómica

Las **nuevas** identidades incluyen `bill_schedule_snapshot`: frecuencia de la
factura, día de anclaje, vencimiento original y clave original de serie. No se
sustituye por `schedule_snapshot` de la recurrencia. Las identidades anteriores
siguen siendo legibles; si carecen de esa información, el POST compartido devuelve
409 sin inferirla, migrarla o registrar dinero.

`generate_next_shared_bill` se ejecuta desde ambos orígenes dentro de la misma
transacción del pago. Una factura `once` no genera otra, aunque su recurrencia
sea mensual. Para facturas periódicas solo se crea el siguiente período cuando
el pendiente común llega exactamente a cero. Se reutilizan `_bill_add_period`,
ID UUIDv5 `bill-next:<bill_id>`, verificaciones de colisión y coordinación R3 de
las referencias copiadas. No se adopta una factura existente por coincidencia de
serie/fecha. Cambios posteriores de fechas, frecuencia o anclaje de la factura
original no reasignan sus pagos ni modifican la programación congelada.

La creación deja una prueba interna `next_bill_generation` en la identidad y
`_bill_generation_origin` en la nueva factura, en la **misma transacción**. La
prueba permite verificar reintentos sin volver a crear el período. Si una factura
futura tiene cambios de programación, su procedencia conserva la prueba original;
si falta el documento futuro y su enlace, la prueba impide recrearlo durante la
recuperación del pago (sin reparar el resto del historial). Los guards actuales
impiden esas modificaciones por rutas públicas mientras permanezca reservada. Un enlace colgante o prueba contradictoria se rechaza;
no se repara automáticamente. `_bill_generation_origin` se filtra de todas las
respuestas mediante el serializador común.

La factura futura recién creada reserva su propia identidad compartida en la
misma transacción, sin pagos ni adopción de historial. Su referencia recurrente
se valida para el vencimiento exacto, frecuencia e importes correspondientes;
una programación futura incompatible provoca 409 y rollback de la finalización.
No se busca un vencimiento cercano ni se desvincula silenciosamente la recurrencia.
La reserva evita que desactivar R4 permita pagar ese nuevo período por el flujo
antiguo. La etapa 2D.6 permite únicamente ediciones conservadoras coordinadas;
las eliminaciones o reasignaciones que comprometan padres reservados siguen
bloqueadas.

Un fallo en generación aborta también identidad nueva, pago, recibos, movimiento
actualización de saldo y enlaces. Un commit incierto mantiene el 503 anterior:
puede haberse guardado todo. Se reutiliza la misma clave y payload; no se genera
una intención nueva ni se presenta el error como rollback confirmado.

### Pruebas y límites de activación

```bash
python3 -B -m unittest backend.tests.test_shared_dispatch
MONEYFLOW_R4_DISPATCH_REAL_TESTS=1 python3 -B -m unittest backend.tests.test_shared_dispatch_mongodb
```

Las pruebas usan exclusivamente fixtures nuevos `test_r4_core_<UUID>`, con
destino/topología verificados y auditoría de comandos. Se instalan índices solo
en esas bases sintéticas nuevas; se conservan. La activación en las pruebas es
configuración en memoria, no modificaciones de `.env` ni de un entorno existente.

Se prueban ambos órdenes de origen, parciales iguales, cuentas iguales/distintas,
conflictos reales 112, mismo ID concurrente, dos intentos de completar, rollback,
commit confirmado con respuesta perdida, factura `once`, programación congelada,
identidades antiguas incompletas, siguiente período y ausencia de metadatos.

Las etapas 2D.5, 2D.6 y 2D.7 completaron link/mark, edición conservadora de
padres y recuperación persistente de Facturas/Recurrencias. Su journal es
independiente del de deudas R6 y conserva la intención entre reinicios.
Completar la integración **no autoriza la activación** en un entorno real:
los guards siguen bloqueando las escrituras R4 cuando el interruptor está apagado.
No se modifica Emergent ni se provisiona ningún entorno.


## Etapa 2D.4 — anulación financiera y retirada de seguimiento

Los dos DELETE seleccionan el adaptador compartido dentro de la misma
`payment_transaction`, antes del guard y del no-op antiguo para recibos retirados.
No se cambia el manejador transaccional ni se abren transacciones anidadas.
Sin historial R4 se conserva el flujo anterior; con R4 desactivado los guards
siguen rechazando obligaciones gestionadas, incluso con recibos retirados.

- `DELETE /api/bills/payments/{pid}` anula el gasto compartido.
- `DELETE /api/recurring-payments/payments/{pid}` anula si el registro original
  es `expense`; si es el recibo complementario `link` de un pago de factura,
  retira exclusivamente el seguimiento recurrente.
- La selección verifica los IDs y la cápsula original de ambos recibos.
  Un modo alterado o un historial incompatible devuelve 409; no se adopta ni
  repara automáticamente información histórica.

La anulación elimina un único movimiento, conserva ambos recibos anulados y
recalcula el saldo una vez. Una repetición sobre el evento ya anulado no escribe
ni devuelve dinero de nuevo. Una retirada conserva el movimiento y el dinero
pagado; no reabre el pendiente. Es posible retirar el `link` y después anular
el pago desde Facturas, usando su ID original. El DELETE no crea claves ni
intenciones nuevas. Las respuestas conservan `{ "ok": true }` y no incluyen
metadatos privados. Los PUT/DELETE genéricos de movimientos siguen bloqueados.

La revisión compartida y las escrituras de padres/movimiento producen conflictos
reales entre anulaciones, retiradas y pagos concurrentes. El manejador existente
reintenta la transacción completa con lecturas actualizadas. Antes de eliminar
el gasto se conserva la protección R3 de `recurring_templates.source_transaction_id`:
409 sin cambios si el movimiento es origen de una plantilla. Retirar un `link`
no borra ese movimiento y puede conservar legítimamente la plantilla.

### Política de factura futura ya generada

Se conserva la política del DELETE anterior: anular el pago de un período no
borra, modifica ni reprograma la factura futura ya generada ni su reserva R4.
También permanece la prueba `next_bill_generation` del período original.
El pendiente financiero del período anulado vuelve a reflejar el dinero real;
el período siguiente continúa siendo una obligación distinta. Volver a pagar
el período original no genera una segunda factura futura. No se completa ni
repara una programación histórica incompleta automáticamente.

Un error intermedio aborta movimiento, recibos, enlaces, revisión y saldo.
Un commit incierto conserva el 503 existente: el reembolso puede haberse
confirmado. Repetir el DELETE con el mismo ID verifica el estado actual y no
reembolsa dos veces. No se interpreta 503 como rollback confirmado.

### Verificación y límites

Las pruebas de los dos DELETE se incluyen en `test_shared_dispatch` y
`test_shared_dispatch_mongodb`, con los mismos comandos de la sección 2D.3.
Cubren devolución desde ambos orígenes, retirada y posterior anulación,
repeticiones, concurrencia real, saldos/historial, bloqueo por plantilla,
fallo antes del recálculo y después de todas las escrituras, resultado incierto,
flag desactivado, contexto inválido, modo corrupto, facturas futuras y rutas
genéricas bloqueadas. Se fuerzan ambos órdenes de confirmación entre creación
de plantilla y anulación: la plantilla confirmada protege el gasto; el gasto
anulado impide crear una plantilla huérfana, tras conflicto y revalidación. MongoDB usa exclusivamente bases nuevas sintéticas,
verificadas antes de escribir y conservadas al terminar.

Las etapas 2D.5 a 2D.7 completaron link/mark, edición coordinada de padres y
recuperación persistente de intenciones de Facturas/Recurrencias.
La retirada de seguimiento de factura (`retire_bill`) y de ambas vistas
(`retire_both`) existe en el núcleo pero no tiene una ruta pública nueva:
el DELETE de Facturas conserva su significado financiero de anulación.
R4 permanece desactivado por defecto y esta etapa no autoriza su activación.


## Etapa 2D.5 — seguimiento administrativo independiente

Con R4 habilitado y contexto verificado, el selector transaccional existente
admite `mark` y una forma limitada de `link`. El interruptor permanece desactivado
por defecto. Las operaciones heredadas sin historial R4 no cambian; los guards
bloquean las obligaciones R4 cuando el interruptor está desactivado.

`link` restaura únicamente el recibo recurrente `link` retirado de un pago R4
originado en Facturas. Exige un movimiento activo, su cápsula original y los dos
recibos verificables del mismo contexto, usuario, obligación y vencimiento.
El recibo de factura debe seguir activo. Un seguimiento activo, un pago anulado,
otro período/usuario, un importe/cuenta/categoría incompatibles o un movimiento
anterior a R4 producen 409 sin cambios. No se adoptan movimientos históricos.

Se restauran los enlaces originales y el estado del recibo recurrente; los IDs,
las cápsulas financieras, el importe y los saldos permanecen intactos. No se crea
un pago ni un movimiento, no se recalcula el saldo y no se genera otro período.
La respuesta conserva los campos del contrato recurrente y devuelve el ID del
recibo original restaurado. La intención administrativa tiene su propio ID
interno, derivado del ID que el endpoint ya genera para esa Idempotency-Key.

`mark` crea solamente un registro de seguimiento con `transaction_id=null` y
`settles=false`. Conserva el payload original, incluido un `settles=true`
solicitado, en una cápsula administrativa privada, sin presentarlo como dinero
liquidado. No crea recibos financieros, movimientos ni descuentos. Una marca R4
verificable no reduce el pendiente y no impide un pago `expense` posterior.
Las marcas históricas sin procedencia verificable conservan el bloqueo de
conciliación anterior; no se convierten automáticamente en marcas nuevas.
El DELETE recurrente retira la marca dentro de la misma transacción, conservando
su historial y sin modificar movimientos o saldos.

### Journal e idempotencia

La colección `shared_tracking_intents` conserva un documento por intención:
ID determinista, usuario, cápsula (entorno, obligación, ID de intención, payload
exacto y fingerprint), ID del recibo objetivo y respuesta pública original.
No se acumulan listas ilimitadas dentro de una obligación o recibo financiero.
Solo se consulta por el índice nativo `_id_`; no se introducen índices adicionales.
La colección debe provisionarse explícitamente antes de una futura activación:
si no existe su índice nativo, el adaptador devuelve 503 antes de escribir.
No se crea durante el arranque ni se provisiona en entornos existentes.

La revisión escrita de la obligación coordina marcas, restauraciones y dinero.
Reintentos idénticos recuperan la respuesta si el seguimiento sigue verificable,
sin nuevas escrituras. Payload distinto con la misma clave devuelve 409.
Una intención nueva no puede restaurar seguimiento ya activo. Si posteriormente
se retira o anula, el reintento antiguo no vuelve a activarlo; devuelve 409.
Un commit incierto conserva 503: puede haberse confirmado todo. Se reutilizan la
misma clave y el payload original, sin interpretar el error como rollback.

Las escrituras del journal y del seguimiento se confirman juntas. Los fallos
abortan también revisión y enlaces. Los serializadores ocultan las cápsulas y
los campos `_shared_*`; ninguna API pública expone el journal. Las lecturas
comunes siguen calculando dinero a partir de movimientos únicos, incluyendo
pagos con seguimiento retirado. Los PUT/DELETE genéricos siguen bloqueados.

Las pruebas de `test_shared_dispatch` y `test_shared_dispatch_mongodb` incluyen
restauración, repetición, retirada, anulaciones, contextos y movimientos ajenos,
marcas seguidas de pagos, lecturas públicas, rollback, respuesta perdida y
conflictos reales entre intenciones iguales/diferentes y operaciones financieras.
Se usan únicamente bases nuevas sintéticas; el journal se crea solo en esos
fixtures. No se activa R4 ni se modifica Emergent. La edición coordinada de
padres y la recuperación persistente del cliente se implementaron en 2D.6 y 2D.7.
Esta etapa no autoriza activar R4 en entornos reales.


## Etapa 2D.6 — edición conservadora de padres compartidos

El PUT de Facturas, PUT de Recurrencias y pause/resume/end seleccionan el contexto
compartido dentro de la `payment_transaction` existente, antes del guard antiguo.
No hay transacciones anidadas ni modificaciones del manejador. Con interruptor
apagado permanecen los bloqueos; sin gestión R4 sigue el flujo heredado.

El contexto verifica entorno, identidades, recibos, movimientos e historial. Las
revisiones de las obligaciones se escriben antes de validar/tocar sus padres,
con el mismo orden que los pagos. La concurrencia fuerza conflictos y reintentos
completos con lecturas actualizadas. Un error de consulta no significa ausencia.

### Facturas

Se permite editar información descriptiva y referencias predeterminadas válidas.
Las cuentas/categorías de movimientos y recibos anteriores nunca cambian. Los
campos de referencia omitidos conservan sus valores literales mediante R3.
No se permite cambiar fecha, frecuencia o recurrencia de una factura reservada.

El importe real puede actualizarse, en la factura y su identidad dentro de la
misma transacción, únicamente si no queda por debajo del dinero pagado y no hace
incompatible la generación comprometida. No cambia el importe previsto histórico,
las cápsulas, recibos ni movimientos. Ejemplos: un importe 90 para factura once
con 60 pagados deja 30 pendientes; 59 devuelve 409. Una mensual fija prevista en
100 no puede bajar a 80 si su próxima factura quedaría incompatible. Una variable
puede cambiar su importe real si sigue siendo compatible con su programación.

La comprobación del siguiente período es de solo lectura. Usa la frecuencia,
anclaje y vencimiento originales; comprueba referencias que se copiarían y la
compatibilidad recurrente antes de guardar. Si ya hay factura futura, verifica
su prueba y reserva, pero no propaga el importe ni las cuentas editadas a ella.
No se generan facturas desde un PUT ni se reparan reservas perdidas.

### Recurrencias y estados

Se permiten nombre, notas, aspecto y referencias predeterminadas validadas,
conservando programación y dinero históricos. En el flujo compartido, end_date
y variable omitidos conservan su valor. Cambiar variable requiere una política
separada y permanece bloqueado.

Cuando hay facturas periódicas comprometidas, permanecen bloqueados los cambios
de programación/importe previsto/finalización que afecten su cadena original.
No se traslada silenciosamente el calendario ni se omite la siguiente factura.
Cuando todas las reservas son once, se permite una nueva versión cuya fecha de
inicio explícita sea posterior a hoy, a todas las reservas, facturas vinculadas,
registros conocidos y la versión anterior. Se añade la versión con esa fecha;
no se sobrescriben versiones anteriores ni se infiere otro corte temporal.

Pause/resume/end permanecen bloqueados cuando afectan una reserva presente o
futura o una cadena periódica. Son admisibles para obligaciones once anteriores
a hoy, sin facturas/registros comprometidos presentes o futuros; sus períodos
originales conservan el historial y siguen siendo pagables. Se mantienen las
validaciones y respuestas existentes de los tres estados.

### Creación y eliminación

Los POST de creación mantienen sus validaciones, IDs y guards existentes: no
adoptan identidades ni historial y no reasignan una reserva. Las eliminaciones
siguen devolviendo 409 para padres R4 necesarios, incluso reservas sin pagos,
recibos anulados e identidades históricas. No hay cascadas, archivado automático,
retirada de identidades ni limpieza de futuras facturas.

Los conflictos de política son 409 con rollback completo. El 503 de commit
incierto no afirma que el cambio se deshiciera; se consulta el estado actual.
Ninguna edición devuelve dinero ni crea pagos. Se conservan las formas públicas
y el serializador oculta metadatos de coordinación, generación e intenciones.

Las suites de dispatch incluyen $60/$100, importes compatibles/incompatibles,
cuentas históricas, once, reserva futura, cambios futuros seguros, estados,
historial incoherente, rollback y resultados inciertos. Las pruebas reales
fuerzan conflictos entre pagos y cambios de importe/cuenta/descripción/estado.
R4 sigue apagado; no se provisionan ni consultan bases existentes.

Límites: no se habilita el cambio de modalidad fija/variable ni una nueva política
para reemplazar cadenas periódicas comprometidas. Recurrencias con historiales
muy grandes requieren medir el coste de verificar/bloquear sus identidades en
una transacción antes de activar R4. La recuperación persistente del cliente
para Facturas/Recurrencias está implementada en 2D.7; no autoriza activación.


## Etapa 2D.7 — contexto del cliente y recuperación persistente

**No existe autenticación.** MoneyFlow declara `single_user` y el usuario efectivo
`default-user` establecido por el servidor. Las cabeceras comprueban consistencia
de contexto, no identifican a una persona ni autorizan acceso. Esta protección
no sustituye autenticación ni controles de acceso necesarios antes de publicar
MoneyFlow para usuarios reales.

Ambos POST de pagos aceptan opcionalmente las cabeceras R6
`MoneyFlow-Environment-ID` y `MoneyFlow-User-ID`. Sin cabeceras se conserva el
contrato anterior, sin garantía de contexto declarado por esos clientes. Con
una sola cabecera se devuelve 422; con ambas se compara el metadato y pin efectivos
y `default-user` dentro de la misma `payment_transaction`, antes de seleccionar
flujo R4/heredado o escribir. Discrepancias devuelven 409 y contexto no verificable
503. Cabeceras vacías/excesivas se rechazan mediante validación del endpoint.
No se configura un entorno, no se provisiona metadata y no se activa R4.

`GET /financial-context` declara las capacidades
`bill_payment_context_headers` y `recurring_payment_context_headers` verdaderas
para estos endpoints. El frontend nuevo exige ambas, un UUID válido y modo
`single_user/default-user`; si faltan capacidades/contexto bloquea el envío y
ofrece verificación manual. No envía sin cabeceras como alternativa. Entornos
sin metadata/pin deben configurarse explícitamente antes de usar este flujo
protegido; no se modifica Emergent. Esto funciona también con R4 apagado y con
facturas/recurrencias heredadas en un contexto provisionado.

### Persistencia local

AsyncStorage existente guarda un registro versionado en
`moneyflow:obligation-payment:v1`. Conserva clave de idempotencia, tipo e ID de
entidad, vencimiento original, payload exacto (incluidos fecha, modo y referencias),
contexto efectivo y estado `pending/conflict/confirmed`. La confirmación guarda
solo los campos mínimos de respuesta necesarios para verificarla. No se guardan
tokens, credenciales, perfil de usuario ni campos adicionales del servidor.
Los journals de deuda R6 y los metadatos MongoDB no se migran ni modifican.

Se conserva una única intención sin resolver entre las dos pantallas y contextos
de esta instalación, de forma conservadora. No puede eludirse abriendo otra
factura, recurrencia, período o cambiando URL/entorno. Los alias del mismo entorno
mantienen identidad. Cada recuperación/envío verifica contexto/capacidades y el
servidor vuelve a verificarlo dentro de la transacción del POST.

El contexto verificado al abrir la pantalla queda fijado para una nueva intención.
Si cambia antes del primer envío, se bloquea y se requiere volver a abrirla, sin
crear una clave ni aceptar silenciosamente el nuevo contexto.
La intención se escribe y relee antes del POST. Un fallo de lectura, escritura,
validación o readback bloquea el envío. La cola compartida por el almacenamiento
y los guards de pantalla impiden crear dos intenciones por doble toque/remonte.
El payload enviado es una copia del registro guardado; un reintento no vuelve a
leer importes, cuentas, fecha del dispositivo o formulario para construirlo.
Abrir una pantalla solo recupera el journal y contexto: nunca envía un pago.

Una respuesta perdida, 503 o fallo al persistir confirmación conserva la intención.
`Reintentar pago anterior` envía manualmente la misma clave y payload. Un 409 o
respuesta incompatible conserva evidencia como `conflict` y bloquea reenvío;
`Verificar registro` consulta explícitamente los endpoints de conciliación de
solo lectura descritos en la sección de cierre, con la clave, payload y contexto
originales. No crea claves ni pagos. Solo una aplicación original íntegramente
verificada permite cerrar la intención; ausencia, discrepancia o resultado no
verificable conservan el journal bloqueado. No se deduce confirmación por igualdad
de importes ni se borra evidencia a ciegas.
Los demás rechazos tampoco autorizan a sustituir automáticamente la intención.

La confirmación se persiste antes de invalidar consultas y limpiar exclusivamente
su clave. Si falla el refresco/limpieza se conserva la confirmación para continuar
sin POST adicional. Mientras se cierra la pantalla sigue bloqueado el botón.
Una respuesta tardía tras desmontar/cambiar de ruta no navega sobre otra pantalla;
la confirmación queda disponible para recuperar. Un segundo pago legítimo necesita
una nueva acción explícita tras resolver el anterior y obtiene una nueva clave.

### Consultas y presentación

Se invalidan `bills`, `bill`, `bills-summary`, `rp-list`, `rp-overview`, `rp-detail`,
`rp-occ`, `rp-cand`, `accounts`, `transactions`, `summary`, `calendar-events`,
`calendar-summary` y `calendar-upcoming`. El helper se comparte también con
mutaciones de Facturas y edición/eliminación de Recurrencias para evitar vistas
cruzadas desactualizadas. La invalidación hace las consultas obsoletas; un fallo
de red puede impedir obtener datos frescos y no cambia el resultado financiero.

No se alteran definiciones de estilos, fuentes, tamaños ni navegación. Se añade
solo estado mínimo pendiente/confirmado/discrepante y acciones de recuperación.
Los datos recuperados se muestran bloqueados y se suprimen proyecciones de un
segundo descuento. Las pruebas físicas de estas pantallas siguen pendientes.

### Verificación y límites

`node frontend/scripts/test-obligation-payment-journal.cjs` usa exclusivamente
almacenamiento/transporte sintéticos y cubre respuesta perdida, reinicio,
doble toque, fechas distintas, contexto/usuario, capacidades ausentes, conflicto,
fallos de almacenamiento, limpieza fallida, segundo pago legítimo e invalidaciones.
Los tests backend de dispatch prueban ambos protocolos con y sin R4 en memoria y
MongoDB nuevo, incluyendo cabeceras correctas, incorrectas, parciales y malformadas.

No se recuperan intenciones anteriores a esta versión que nunca se guardaron.
No hay recuperación entre dispositivos, reinstalaciones ni garantía de exclusión
entre procesos independientes/pestañas: la cola coordina la misma instancia de
almacenamiento del runtime de la app. Un cambio de período/entidad/contexto no
reasigna el registro; se bloquea hasta resolverlo. La identidad de clones debe
seguir las reglas de provisionamiento R6. R4 permanece desactivado y no se
habilita ni configura Emergent.

## Correcciones de cierre: contexto DELETE y candidatos verificables

Los DELETE de pagos de Facturas y Recurrencias aceptan opcionalmente las mismas
cabeceras de contexto R6 que los POST. Con ambas cabeceras se verifica entorno
efectivo y `default-user` dentro de `payment_transaction`, antes de anular dinero
o retirar seguimiento. Cabeceras parciales/vacías/excesivas se rechazan con 422;
discrepancias con 409 y contexto no verificable con 503, sin escrituras.
Sin cabeceras permanece la compatibilidad anterior, sin garantía de intención de
contexto del cliente. Esto no constituye autenticación.

El contexto declara `bill_payment_delete_context_headers` y
`recurring_payment_delete_context_headers`. Las pantallas de detalle fijan el
contexto observado al cargar los datos; antes de anular verifican nuevamente
capacidades y coincidencia, y envían las cabeceras. No sustituyen silenciosamente
ese contexto después de un refresco ni envían sin protección como alternativa.

`link-candidates` utiliza una instantánea de lectura compartida. Para un período
R4 ofrece exclusivamente gastos activos de Facturas cuyo seguimiento `link`
original esté retirado, tras verificar identidad, período, recibos, intención,
referencias y la misma prueba que utiliza la restauración transaccional. No crea
movimientos ni descuenta dinero. Gastos anulados, de otro período o con seguimiento
activo no son candidatos. Historial incoherente produce 409 y errores MongoDB 503;
las respuestas se sanean sin revelar procedencia interna. Para períodos sin R4
permanece la selección heredada, excluyendo cualquier procedencia R4.

### Conciliación verificable de intenciones (consulta, sin escrituras)

Se implementaron `POST /api/bills/{bid}/payments/reconcile` y
`POST /api/recurring-payments/{rid}/payments/reconcile`. Ambos reciben exactamente
el DTO original de su POST financiero y requieren `Idempotency-Key`,
`MoneyFlow-Environment-ID` y `MoneyFlow-User-ID`. La normalización/fingerprint
reutiliza `model_dump()` y el formato original de cada origen; no se sustituyen
fechas, IDs, importe, cuenta ni claves durante la recuperación.

Las consultas verifican el pin R6, metadata y `default-user` antes de leer el
resultado, dentro de una transacción snapshot de lectura. Funcionan con R4
apagado; no ejecutan `payment_transaction`, guards de escritura, incrementos de
coordinación, generación de períodos, adopción, índices ni reparaciones.
Las cabeceras ausentes/parciales/malformadas por longitud producen 422;
discrepancias de entorno/usuario producen 409 antes de devolver recibos, y
problemas MongoDB/contexto no verificable producen 503. No son autenticación.

Respuesta estable version 1:

- `status`: `matched`, `cancelled`, `tracking_removed`, `not_found`,
  `discrepancy` o `unverifiable`.
- `financial_state`: `active`, `annulled`, `none` o `unknown`.
- `original_request_matches`: true solo en los tres resultados coincidentes;
  false en discrepancia de payload, null cuando falta evidencia.
- `environment_id`, `user_id`, `origin`, `parent_id`, `original_due_date` y
  `receipt`. El recibo incluye únicamente ID, usuario, importe, cuenta, fecha,
  movimiento y referencia al padre; para recurrencias incluye modo y vencimiento.
  Resultados no resueltos no devuelven recibo ni procedencia interna.

Para R4 se verifica identidad canónica, revisión/período original, unicidad,
intención y fingerprint, IDs deterministas, ambos recibos y movimiento financiero
único. Se comprueban también fechas y notas originales. La restauración `link`
se consulta mediante su propia intención administrativa y target original,
nunca deduciendo que un gasto igual corresponde a esa solicitud. El journal,
la respuesta guardada y el grafo deben concordar. Una marca `mark` aplicada o
retirada tiene efecto financiero `none`. Una retirada `link` mantiene dinero
`active`; una anulación demostrada por tombstones R4 tiene estado `annulled`.

Para flujos heredados se exige el fingerprint original, padre y grafo activo
íntegro. No se adopta historial. En facturas heredadas el payload no conserva el
vencimiento original: su identidad es el ID de factura; `original_due_date` se
devuelve null, sin inferirlo a partir de la fecha actual ni asignar una obligación
compartida. Tombstones heredados sin estado financiero explícito permanecen
`unverifiable`: no basta un flag deleted y un movimiento ausente para demostrar
una devolución. Un evento parcial no se clasifica como ausencia.

`not_found` describe exclusivamente el snapshot consultado. No demuestra rollback
ni descarta una operación concurrente todavía no visible; conserva estado
financiero `unknown` y nunca autoriza otra clave. Una conciliación concurrente
con anulación puede observar la instantánea anterior o posterior, siempre íntegra.

### Recuperación manual en las pantallas

El contexto declara `bill_payment_reconciliation` y
`recurring_payment_reconciliation`. El cliente exige la capacidad correspondiente
antes de crear una intención nueva; no usa un backend sin recuperación como
alternativa silenciosa. Los registros anteriores siguen siendo legibles y no se
migran ni eliminan automáticamente.

`Verificar registro` consulta la intención con exactamente el journal conservado.
No llama al POST financiero ni a retry, y no genera claves. Una prueba coincidente
se persiste como `reconciled`, con recibo mínimo y resolución, antes de cualquier
limpieza. Luego se invalidan Facturas, Recurrencias, Cuentas, Movimientos,
Resúmenes y Calendario. Se muestra pago confirmado, operación anulada o seguimiento
retirado según corresponda; mark nunca se presenta como dinero pagado.

La acción separada `Cerrar verificación` limpia exclusivamente esa clave ya
verificada y vuelve a la pantalla anterior. No paga ni repite operaciones anuladas
o retiradas. Un nuevo pago legítimo exige otra acción explícita posterior.
Ausencia, discrepancia, error de red, capacidad ausente, contexto distinto,
historial incompleto o fallo de persistencia mantienen la intención bloqueada.
No existe un botón de descarte de conflictos ni reenvío financiero automático.
Un reinicio/limpieza fallida conserva la resolución y evita otro descuento.
Abrir una pantalla solo recupera almacenamiento/contexto; no paga ni concilia
automáticamente. Los estilos y navegación general permanecen intactos.

Las pruebas de dispatch comparan todos los documentos antes y después de cada
consulta y verifican ausencia de comandos MongoDB de escritura. Incluyen ambas
rutas, anulaciones, link/mark retirados, ausencia, discrepancia, contexto,
historial incompleto y concurrencia real en bases nuevas sintéticas. El script
frontend verifica recuperación, 409, payload/clave congelados, resolución durable,
fallos de almacenamiento/red y los handlers reales. La prueba física Samsung
continúa pendiente. R4 sigue desactivado y no se configura Emergent.
