# Resultados BM Sanse en Firebase Spark

Aplicación web estática para consultar los resultados de BM Sanse en el Campeonato de España de Balonmano Playa de Laredo 2026.

## Versión gratuita

El proyecto utiliza únicamente **Firebase Hosting**, compatible con el plan gratuito Spark y sin necesidad de asociar una tarjeta o cuenta de facturación.

- `public/`: interfaz responsive y datos que se publican en Hosting.
- `public/data/resultados.json`: resultados disponibles para cada fecha.
- `actualizar_datos_web.py`: actualiza ese archivo desde las fuentes públicas de RFEBM/iSquad.
- No utiliza Cloud Functions, Cloud Run, Firestore ni otros servicios de pago.

Al ser una web estática, los resultados no se consultan directamente desde Firebase. Para incorporar marcadores nuevos hay que ejecutar el actualizador y volver a publicar Hosting.

## Requisitos

- Python 3 para actualizar los resultados.
- Firebase CLI para probar y publicar la web.
- Un proyecto Firebase en el plan gratuito **Spark**.

## Crear y vincular el proyecto gratuito

1. Crea un proyecto en [Firebase Console](https://console.firebase.google.com/).
2. Mantén seleccionado el plan Spark; no vincules una cuenta de facturación.
3. Desde esta carpeta, inicia sesión y selecciona el proyecto:

   ```bash
   firebase login --reauth
   firebase use --add
   ```

También puedes copiar `.firebaserc.example` como `.firebaserc` y sustituir el identificador de ejemplo.

## Actualizar los resultados

Por defecto se descargan las cuatro jornadas de Laredo 2026:

```bash
python3 actualizar_datos_web.py
```

También puedes indicar fechas concretas:

```bash
python3 actualizar_datos_web.py 2026-07-31 2026-08-01
```

El actualizador conserva los datos anteriores de las fechas que no se hayan solicitado. Así se puede actualizar solo la jornada actual sin perder las demás.

Si la consulta devuelve exactamente los mismos marcadores, el archivo no se modifica. De esta forma GitHub no crea un commit ni despliega Firebase innecesariamente.

## Actualización automática con GitHub

El flujo `.github/workflows/actualizar-resultados.yml` consulta la jornada actual cada quince minutos, entre las 08:00 y las 22:59 de los días del campeonato, usando la zona horaria de Madrid.

1. En GitHub, abre **Settings → Actions → General**.
2. En **Workflow permissions**, selecciona **Read and write permissions**.
3. Guarda el cambio.

Cuando hay un marcador nuevo, el flujo actualiza `public/data/resultados.json` y crea un commit. Ese commit activa `firebase-hosting-merge.yml`, que publica la web. Si no ha cambiado ningún resultado, no se crea el commit ni se despliega Firebase.

También puedes ejecutarlo manualmente desde **Actions → Actualizar resultados BM Sanse → Run workflow**.

## Probar en local

```bash
firebase emulators:start --only hosting
```

La aplicación estará disponible en `http://127.0.0.1:5050`.

## Publicar sin coste

```bash
firebase deploy --only hosting
```

Firebase mostrará la URL pública al terminar. Para publicar nuevos resultados, repite la actualización y el despliegue de Hosting.

## Actualizar otro campeonato

El script `consultar_resultados_sanse.py` descubre las categorías y grupos a partir de la URL oficial indicada en `DEFAULT_SEED_URL`. Si la RFEBM crea una nueva edición, cambia esa URL y las fechas predeterminadas de `actualizar_datos_web.py`.
