// Capa de rótulos (español). Para traducir: copia este archivo (p. ej. rotulos.en.js),
// traduce los valores y cambia el <script src> en index.html.
window.EG_TEXT = {
  brand: 'evalgate',
  scenes: {
    Adopcion: 'Adopción',
    Contabilidad: 'Reenvío y cuenta',
    Desconexion: 'Cliente cortado',
    Telemetria: 'Telemetría',
    Degradacion: 'Almacén caído',
    Precios: 'Precios',
    Emparejado: 'Evaluación emparejada',
    Estadistica: 'Estadística',
    Puerta: 'La puerta'
  },
  captions: {
    Adopcion: 'Se adopta cambiando una variable de entorno. Cero código.',
    Contabilidad: 'Reenvía según llega y cuenta en paralelo.',
    Desconexion: 'Cliente cortado = tokens pagados = tokens contados.',
    Telemetria: 'La traza nunca hace esperar a la petición.',
    Degradacion: 'Si el almacén cae, se pierde la traza, no la petición.',
    Precios: 'Ningún precio en el código. Una tabla publicada no se edita: se publica otra.',
    Emparejado: 'Mismos casos, emparejados. El juez nunca es el modelo que genera.',
    Estadistica: '¿La caída es mayor que el ruido?',
    Puerta: 'Un evaluador no evaluado es un adorno.'
  },
  status: { 'hecho': 'hecho', 'en curso': 'en curso', 'pendiente': 'pendiente' },
  lanes: { app: 'Tu app', evalgate: 'Evalgate', provider: 'Proveedor LLM' },
  legend: { traffic: 'tráfico de usuario', accounting: 'contabilidad · tokens y coste', telemetry: 'telemetría · trazas' },
  app: { title: 'Tu app', envKey: 'OPENAI_BASE_URL=', envOld: 'http://localhost:11434/v1', envNew: 'http://localhost:8080/v1', cut: 'conexión cortada' },
  proxy: { title: 'Evalgate', sub: 'proxy · reenvía en streaming' },
  provider: { title: 'Proveedor compatible con OpenAI', sub: 'hoy: Ollama en local' },
  counter: { label: 'tokens contados' },
  record: { title: 'registro de uso', l1: 'entrada 18 · salida 30 tok', l2: 'cliente cortado · flujo completo' },
  queue: { title: 'cola · 4 huecos', full: 'llena', dropped: 'descartados' },
  db: { title: 'ClickHouse', sub: 'trazas', down: 'sin conexión' },
  prices: {
    title: 'tabla de precios', version: 'v3', date: 'publicada 2026-09-14',
    cols: ['modelo', 'entrada', 'salida'],
    rows: [['modelo-a', '0,15', '0,60'], ['modelo-b', '0,50', '1,50'], ['modelo-c', '2,00', '8,00']],
    unit: '€ por millón de tokens', old: ['v1', 'v2'],
    cost: 'coste', costValue: '0,0000207 €', costSub: '18 × 0,15 + 30 × 0,60 · tarifa v3',
    example: 'valores de ejemplo'
  },
  ci: {
    header: 'CI · pull request', generator: 'generador: modelo A', base: 'línea base', branch: 'rama', caseLabel: 'caso',
    orphan: 'caso 07 sin pareja → error: no se compara', judge: 'juez', judgeSub: 'modelo B ≠ generador', cache: 'caché'
  },
  stats: {
    axis: 'diferencia de calidad (rama − línea base)', bootstrap: 'bootstrap · remuestreo de parejas',
    band: 'ruido', threshold: 'umbral', measured: 'diferencia medida',
    inside: 'Dentro del ruido: no hay caída real.', outside: 'La caída supera el ruido.',
    goals: ['GOALS.yaml', 'calidad:', 'max_caida: ‹umbral›', 'confianza: ‹nivel›']
  },
  gate: {
    change: 'cambio', pass: 'exit 0', passSub: 'merge permitido', fail: 'exit 1', failSub: 'merge bloqueado',
    metersTitle: 'el evaluador, evaluado', meters: ['acuerdo con humano', 'falsos positivos', 'efecto mínimo detectable'],
    unmeasured: 'sin medir'
  }
};
