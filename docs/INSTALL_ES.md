# AirFare: instalación en 10 minutos

AirFare vigila los vuelos que elijas y muestra una notificación cuando alguno baja de precio. Funciona en Windows 10 y 11, macOS y Linux.

Necesitas Google Chrome, Microsoft Edge, Brave, Opera o Mozilla Firefox (para los precios de Skyscanner y Aviasales) y conexión a internet. El analista de IA (Claude, ChatGPT o DeepSeek) es opcional: sin él, AirFare sigue avisando de las tarifas más baratas y más rápidas con sus propias reglas. Google Flights con SerpApi también es opcional.

## 1. Descomprime y abre

1. Descomprime **AirFare.zip** en una carpeta que vayas a conservar, por ejemplo `Documentos\AirFare` (no en Descargas ni en una carpeta temporal).
2. Haz doble clic en **AirFare.exe**. Si Windows muestra *«Windows protegió su PC»*, haz clic en **Más información** y luego en **Ejecutar de todas formas**. AirFare no está firmado por un editor, así que Windows pregunta una vez.
3. Haz clic en **Aceptar** para instalarlo. Una ventana muestra el progreso (unos 5 minutos). Si falta Python, ofrece instalarlo: escribe **Y**.

Al terminar, AirFare añade iconos en el escritorio y en el menú Inicio, se inicia con Windows y abre los **Ajustes** en tu navegador. Los siguientes pasos se hacen allí.

**En un Mac o en Linux** no hay AirFare.exe. Descomprime AirFare.zip en una carpeta que vayas a conservar, abre un terminal, escribe `cd ` (con un espacio), arrastra la carpeta de AirFare a la ventana del terminal, pulsa Intro y ejecuta `sh install.sh`. Necesita Python 3.12 o posterior: en un Mac sin él, ofrece instalarlo con Homebrew; en Linux te dice qué paquete instalar (en Debian y Ubuntu, `sudo apt install python3 python3-venv`). Al terminar, AirFare está en el menú de aplicaciones (Linux) o en la carpeta Aplicaciones de tu carpeta personal (macOS), se inicia cada vez que inicias sesión y abre los **Ajustes** en tu navegador.

**Idioma:** cambia entre **EN**, **ES** y **RU** arriba a la derecha de cualquier página de AirFare, en cualquier momento. No se pierde nada de lo que hayas escrito.

## 2. Elige tu analista de IA (basta con uno, o ninguno)

**Sin analista**: en **Analista de IA**, elige **Sin analista**. AirFare registra todos los precios, avisa de las tarifas más baratas y más rápidas y dibuja el panel; solo la mejor opción, el texto del análisis y las búsquedas del precio mínimo necesitan un analista.

**Claude, con una suscripción Claude Pro o Max**: en **Analista de IA**, elige **Claude**, luego **Mi cuenta de Claude**, pulsa **Iniciar sesión en Claude**, entra en la ventana que se abre y luego pulsa **Comprobar de nuevo**.

**Claude, con una clave API de Anthropic** (pago por uso):

1. Inicia sesión en [console.anthropic.com](https://console.anthropic.com), añade saldo en **Billing** y crea una clave en **API keys** (empieza por `sk-ant-`).
2. En **Analista de IA**, elige **Claude**, luego **Una clave API de Anthropic**, pega la clave y pulsa **Guardar clave**.

**ChatGPT, con tu cuenta de ChatGPT** (Plus, Pro, Business y planes similares; sin clave API):

1. Instala tú mismo la app Codex de OpenAI: abre PowerShell y ejecuta `irm https://chatgpt.com/codex/install.ps1 | iex` (el instalador oficial de OpenAI; ver developers.openai.com/codex). En un Mac o en Linux, ejecuta en su lugar `curl -fsSL https://chatgpt.com/codex/install.sh | sh` en un terminal. Consulta las condiciones de OpenAI sobre usar un plan de ChatGPT con Codex desde otro programa.
2. En **Analista de IA**, elige **ChatGPT** y luego **Mi cuenta de ChatGPT**.
3. Pulsa **Iniciar sesión en ChatGPT**, entra en el navegador que se abre y luego pulsa **Comprobar de nuevo**.

**ChatGPT, con una clave API de OpenAI** (pago por uso, unos 0,04 $ por comprobación con el modelo recomendado):

1. Inicia sesión en [platform.openai.com](https://platform.openai.com) y añade saldo en **Billing**.
2. Abre [API keys](https://platform.openai.com/api-keys), pulsa **Create new secret key** y cópiala (empieza por `sk-`).
3. En **Analista de IA**, elige **ChatGPT**, luego **Una clave API de OpenAI**, pega la clave y pulsa **Guardar clave**.

**DeepSeek**, pago por uso (menos de 0,01 $ por comprobación):

1. Regístrate en [platform.deepseek.com](https://platform.deepseek.com) y añade unos dólares en **Top up**.
2. Abre **API keys**, pulsa **Create new API key** y copia la clave (empieza por `sk-`).
3. En **Analista de IA**, elige **DeepSeek**, pega la clave y pulsa **Guardar clave**. AirFare la guarda y muestra tu saldo.

## 3. Instala la extensión del navegador (Skyscanner y Aviasales)

1. En **Fuentes de precios**, marca **Skyscanner**, **Aviasales.ru** o ambas, y elige el navegador en el que funciona la extensión: Chrome, Edge, Brave, Opera o Firefox. Las condiciones de uso de ambos sitios no permiten visitas automatizadas; márcalos solo si te parece aceptable. AirFare abre pocas páginas suyas: consulta **Límites** en *Conviene saber*.
2. En Chrome, Edge, Brave u Opera, abre su página de extensiones (Ajustes muestra la dirección, por ejemplo `chrome://extensions`, y la copia) y activa el **Modo de desarrollador**.
3. Haz clic en **Cargar descomprimida** y elige la carpeta `extension` dentro de tu carpeta de AirFare.

Puede que el navegador te recuerde que hay una extensión en modo de desarrollador. Es normal; déjala activada. Aviasales muestra los precios en rublos; AirFare los convierte a tu moneda.

**En Firefox**, la extensión tiene su propia carpeta, `extension-firefox`, y dos formas de cargarla:

- **Para probarla:** abre `about:debugging#/runtime/this-firefox` (Ajustes muestra la dirección y la copia), haz clic en **Cargar complemento temporal…** y elige `manifest.json` en la carpeta `extension-firefox`. Firefox la quita al reiniciarse.
- **Para conservarla:** fírmala una vez como complemento no listado en addons.mozilla.org. Es gratis y no se publica nada:

1. Inicia sesión en [addons.mozilla.org/developers](https://addons.mozilla.org/developers/) con una cuenta de Mozilla y acepta el acuerdo para desarrolladores.
2. Abre PowerShell en tu carpeta de AirFare (en el Explorador de archivos, escribe `powershell` en la barra de direcciones y pulsa Intro) y prepara lo que vas a subir con un id de complemento propio. Parece una dirección de correo, y nadie más puede haberlo firmado: `.venv\Scripts\python tools\make_firefox.py --zip --id airfare-collector@tunombre.example`. Esto crea `dist\airfare-firefox-<versión>.zip`. En un Mac o en Linux, ejecuta en un terminal en la carpeta de AirFare: `.venv/bin/python tools/make_firefox.py --zip --id airfare-collector@tunombre.example`.
3. Pulsa **Submit a New Add-on**, elige **On your own**, sube el zip, marca solo **Firefox** y pulsa **Continue**. Responde **No** a la pregunta sobre el código fuente y envía la versión.
4. Cuando llegue el correo de que el complemento está firmado (suele tardar unos minutos), ábrelo en **My Add-ons**, abre la versión y descarga el archivo `.xpi` firmado.
5. En Firefox, abre `about:addons`, pulsa el engranaje, elige **Instalar complemento desde archivo…**, selecciona el `.xpi` y pulsa **Añadir**. Se queda instalado aunque Firefox se reinicie.

Cuando AirFare traiga una versión nueva del complemento, repite los pasos 2 a 5 con el mismo id y sube el zip en **Upload New Version**, en la página del complemento.

## 4. Opcional: Google Flights con SerpApi

Solo hace falta si también quieres precios de Google Flights. Si no, sáltate este paso: Skyscanner y Aviasales funcionan sin ello.

1. Regístrate en [serpapi.com](https://serpapi.com/users/sign_up) y confirma tu correo (y tu teléfono, si te lo pide). El plan gratuito da unas 250 búsquedas al mes.
2. Abre [serpapi.com/manage-api-key](https://serpapi.com/manage-api-key) y copia tu **API Key**.
3. En los **Ajustes** de AirFare, en **Fuentes de precios**, marca **Google Flights**. Aparece el campo **Clave de SerpApi**.
4. Pega la clave y pulsa **Guardar clave**. AirFare la guarda al momento (aún no hace falta ningún vuelo) y muestra cuántas búsquedas te quedan este mes.

Cada combinación de fechas usa una búsqueda por comprobación. En **Cuándo comprobar**, AirFare muestra cuántas búsquedas al mes necesita tu horario. Para quitar la clave más adelante, pulsa **Quitar la clave guardada**.

## 5. Moneda, vuelos y alertas

1. En **Moneda**, elige Euro, Libra, Dólar o Rublo, u otra moneda en **Otra**. Todos los precios se comparan y se muestran en ella; los que un sitio muestra en otra moneda se convierten con el tipo de cambio del día.
2. En **Vuelos a seguir**, escribe códigos de aeropuerto o ciudad (LHR, BCN, LOND), una fecha o un rango de fechas, los adultos y, si viajan niños, sus edades (por ejemplo `4, 9`).
3. En **Alertas de precio**, pon un umbral para cada tipo: **Más barato**, **Más rápido** y **Mejor opción**. Cada uno avisa cuando su precio baja el porcentaje que elijas o llega a tu límite de precio. También puedes ignorar viajes muy largos o con autotransbordo.
4. Pulsa **Guardar** y luego **Probar enlaces**.

Listo. AirFare comprueba los precios cada vez que enciendes el ordenador (o con el horario que elijas) y muestra una notificación **LOW PRICE** cuando un precio baja.

## Conviene saber

- **Pestañas del panel:** cada ruta tiene su propia pestaña. Si cambias una ruta (por ejemplo, le das la vuelta), su comprobación anterior se queda en su pestaña hasta que la quites.
- **Límites:** AirFare limita las páginas de Skyscanner y Aviasales que abre (las de ambos sitios cuentan juntas). Con **Personal** (el nivel por defecto), una comprobación abre como máximo 20, las comprobaciones automáticas las abren como mucho una vez cada 6 horas, y como máximo 60 al día, contando las comprobaciones manuales. **Ampliado** permite 40 por comprobación, cada 3 horas y 150 al día, tras un aviso que debes confirmar. Elige el nivel en **Ajustes finos → Límites**. Las páginas que superan un límite se dejan fuera y el panel lo indica; Google Flights (SerpApi) no tiene límite.
- **Icono en el área de notificación:** en **Cuándo comprobar**, marca *Mantener un icono de AirFare en el área de notificación* para tener un icono cuyo menú comprueba precios, abre las páginas y cierra AirFare. En un Mac aparece en la barra de menús; en Linux necesita un escritorio con bandeja del sistema.
- **Actualizaciones:** en **Ajustes finos → Actualizaciones**, pulsa **Buscar actualizaciones**; AirFare también puede buscarlas una vez al día al abrir Ajustes.
- **Exportar:** la pestaña **Historial de precios** exporta los registros mostrados como archivo CSV para Excel.
- **Limpieza:** la pestaña **Limpieza** borra precios antiguos, rutas anteriores del panel, búsquedas, informes y el registro, restablece alertas o empieza conversaciones nuevas con el analista. Cada botón muestra cuánto borra, y también puede limpiar automáticamente tras cada comprobación.
- **Privacidad:** este paquete no contiene claves, inicios de sesión ni historial de precios. Todo lo que introduces se queda en la carpeta `data` de tu PC; en Windows, tus claves API se guardan allí cifradas para tu cuenta de Windows (Windows DPAPI), así que no se pueden leer desde otra cuenta ni desde otro PC. En un Mac se guardan en tu Llavero, y en Linux en tu llavero de claves si está instalado `secret-tool` (sin él se quedan en `data`, legibles solo por tu usuario). No compartas esa carpeta.
- **Otro PC:** instálalo desde el zip de AirFare, no copiando tu carpeta instalada.
- **Desinstalar:** haz clic derecho en `uninstall.ps1`, elige **Ejecutar con PowerShell** y luego borra la carpeta de AirFare. En un Mac o en Linux, ejecuta `sh uninstall.sh` en la carpeta de AirFare y luego borra la carpeta.
