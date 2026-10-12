# R6: activación local y validación completadas

La pantalla selecciona `localPaymentFlow`. El flujo v2 requiere `__DEV__` y una
configuración explícita `EXPO_PUBLIC_R6_LOCAL_V2=1`. El UUID esperado y usuario
proceden de `EXPO_PUBLIC_R6_EXPECTED_ENVIRONMENT_ID` y
`EXPO_PUBLIC_R6_EXPECTED_USER_ID`, en el `.env` local ignorado por Git. Ninguna
identidad de un despliegue está incorporada en el código compartido. Sin opt-in,
otros despliegues conservan el cliente anterior; un build de producción tampoco
activa este interruptor. Con opt-in e identidad ausente/incorrecta se bloquea v2,
sin fallback silencioso al cliente anterior.

La configuración local está aplicada y su contexto verificado. La validación
funcional acordada de R6 fue aprobada, incluidas las comprobaciones físicas en
Samsung. v2 NO está activado en Emergent: requiere configuración explícita y
verificación independiente de su propio contexto; publicar el código no lo activa.
Reiniciar Metro es necesario para que
Expo incorpore las variables públicas al bundle. La API debe verificar el UUID
antes de recuperar y antes de enviar. Estas variables identifican el contexto;
no son secretos ni credenciales de autenticación.

## Secuencia de activación y comprobación

1. Revisar destino, metadatos y UUID propuesto antes de cualquier provisionamiento.
2. Autorizar explícitamente la creación de `moneyflow_metadata/financial-context`
   únicamente en el destino local aprobado. El procedimiento de
   `financial-context.md` crea un documento, nunca reemplaza uno existente.
3. Configurar y verificar el identificador esperado en el backend local; comprobar
   la API de contexto y su usuario efectivo `default-user`, modo `single_user`.
4. Revisar por separado los registros v1 existentes. No se migran, borran ni
   reasignan por similitud de URL, monto o deuda. Su presencia bloquea el flujo v2.
5. Configurar el contexto aprobado y el opt-in únicamente en el `.env` local
   ignorado. Esto no debe publicarse como activación general de Emergent ni
   copiarse a sus variables de despliegue. No desactivar el opt-in ni volver al
   cliente anterior mientras exista una intención v2 sin resolver.
   Además, el coordinador v1 revisa todos los registros v2 sin depender del opt-in
   ni de la URL: un pendiente, discrepancia, registro corrupto o fallo de lectura
   bloquea el envío. Las confirmaciones v2 con estructura y recibo válidos se
   conservan y no impiden un pago legítimo. No hay migración automática.
6. Verificar en Samsung con datos sintéticos aislados antes de pagos reales.

## Flujo local validado

Abrir la pantalla solo verifica el contexto y recupera el registro; no envía pagos.
Tras un fallo de recuperación, «Verificar registro» repite la recuperación y la
consulta de conciliación. Puede persistir una confirmación local verificable,
pero no crea claves ni pagos. Un resultado incierto conserva el registro y el
bloqueo de una intención nueva; el reintento financiero requiere otro clic.
El UUID y usuario deben coincidir con el contexto aprobado, independientemente de
la URL. Los fallos de contexto o almacenamiento bloquean el envío.

Una intención nueva se persiste y verifica antes del envío. Una intención recuperada
conserva todos los campos y la clave: al pulsar el botón primero se concilia. Un pago
coincidente se confirma localmente sin volver a enviarlo, incluso si fue editado
después. Un `not_found` permite únicamente reintentar la intención pendiente con
su clave y payload originales. Un registro con discrepancia no se reenvía por un
`not_found`. Pago anulado, discrepancia y resultado no verificable se conservan y
bloquean el envío; no existe aquí un mecanismo de borrado para resolverlos.

La confirmación se verifica en almacenamiento antes de mostrarla. La limpieza solo
se realiza tras el clic explícito «Registrar nuevo pago». Si falla, no se envía otro
pago. El segundo pago necesita una nueva intención y clave. La recuperación no
muestra una proyección adicional de descuento ni permite editar el payload anterior.

Las pruebas automatizadas del flujo y del manejador real de pantalla usan
almacenamiento y servidor sintéticos. También se completaron 12 escenarios de
integración con MongoDB real en una base temporal aislada y las pruebas físicas
acordadas en Samsung: pérdida de respuesta, reinicio de Expo Go, recuperación sin
duplicación, segundo pago legítimo y actualización correcta de saldos y movimientos.
El botón «Verificar registro» recuperó el estado confirmado después de restaurar
una consulta temporalmente fallida, sin registrar otro pago.

El bloqueo al regresar de v2 a v1 se comprobó en el navegador del Samsung con el
código real y registros sintéticos en memoria: PASS pending, PASS conflict, cero
solicitudes de pago y cero claves nuevas. Esta comprobación aislada no desactivó
v2 en Expo Go ni alteró su almacenamiento.

Las pruebas automatizadas no sustituyen las comprobaciones físicas anteriores ni
garantizan durabilidad frente a corrupción del sistema operativo. No cubren
desinstalación ni sincronización entre dispositivos. La base temporal del Samsung
se conserva; su limpieza requiere autorización explícita.
