# ✍️ Writing Agent

[English](README.md) | [Français](README.fr.md) | [Español](README.es.md) | [中文](README.zh.md) | [Nederlands](README.nl.md) | [Русский](README.ru.md) | [한국어](README.ko.md)

**Agente de escritura IA indetectable — Herramienta CLI y framework multi-agente**
*Impulsado por la metodología Ghost Protocol*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-green.svg)](https://nodejs.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

> **El mejor contenido generado por IA es el que nadie sabe que es generado por IA. No porque engañe — sino porque es realmente bueno.**

Writing Agent es una herramienta CLI de código abierto y un framework multi-agente que produce escritura de calidad humana calibrada para pasar los sistemas de detección de IA. Construido sobre inteligencia de ingeniería inversa de más de 50 artículos académicos, documentación de detectores comerciales, estudios de benchmarking de detección y **análisis periodístico real de más de 40 artículos de Harvard Business Review, ESPN, CNN, Wall Street Journal, Yahoo Finance, Search Engine Land y Search Engine Journal**.

**Esto NO es una herramienta de humanización.** Los humanizadores toman contenido IA mediocre y lo maquillan. Writing Agent genera contenido auténtico de calidad humana desde cero — informado por exactamente qué buscan los detectores, por qué, y cómo escriben realmente los periodistas.

### Novedades en v2.0 (Marzo 2026)

- **Inteligencia informada por el periodismo** — Análisis de más de 40 artículos de HBR, ESPN, CNN, WSJ, Yahoo, SEL, SEJ para extraer patrones de escritura humana auténticos
- **Lista negra de 200+ frases** — Expandida de 100 a 200+ frases prohibidas de sonido IA incluyendo variantes
- **Motor de post-procesamiento** — `humanizeContent()` elimina programáticamente patrones de conclusión IA, adjetivos compuestos, pares de atenuación y estructuras de párrafo uniformes
- **Detección de 8 patrones IA** — Nuevas señales: aperturas IA, frases hechas, Q&A retórico, tricolones, párrafos uniformes, conclusiones IA, abuso de guiones largos
- **Controles QA reforzados** — Varianza de longitud de párrafo, detección de tricolones, detección de Q&A retórico, detección de oraciones de apertura IA
- **Sin más frases firma** — Los perfiles de voz ya no tienen "muletillas" sobreusadas
- **Reglas anti-patrón** — Reglas explícitas contra estructura de ensayo, analogías deportivas hilvanadas, listas de tres, patrones tesis-conclusión

---

## Tabla de contenidos

- [Cómo funciona](#cómo-funciona)
- [Arquitectura](#arquitectura)
- [Instalación](#instalación)
- [Inicio rápido](#inicio-rápido)
- [Referencia CLI](#referencia-cli)
- [Tipos de contenido](#tipos-de-contenido)
- [El sistema QA de 40 puntos](#el-sistema-qa-de-40-puntos)
- [Adaptadores de plataforma](#adaptadores-de-plataforma)
- [Perfiles de voz](#perfiles-de-voz)
- [Configuración](#configuración)
- [Wiki y ejemplos](#wiki--ejemplos)
- [Investigación y citas](#investigación--citas)
- [Contribuir](#contribuir)
- [Licencia](#licencia)

---

## Cómo funciona

Ghost Protocol v2 opera sobre cuatro leyes fundamentales:

1. **Patrones informados por el periodismo** — Cada pieza sigue patrones de escritura extraídos de artículos reales de HBR, ESPN, CNN, WSJ y SEL. Los escritores reales comienzan con una escena o hecho, usan metáforas una vez y las abandonan, varían salvajemente la longitud de párrafos, y terminan con detalles específicos — no resúmenes.
2. **Sin disfraz IA** — En lugar de añadir "personalidad" a través de frases hechas, el sistema elimina patrones de sonido IA programáticamente. 200+ frases en lista negra, 8 detectores de patrones estructurales IA, y un motor de post-procesamiento que elimina la jerga corporativa.
3. **Voz sin muletillas** — Los perfiles de voz definen hábitos estructurales (distribución de longitud de oraciones, patrones de párrafos, uso de conjunciones), no frases firma. Los escritores reales no tienen muletillas.
4. **Arquitectura invisible** — La evasión de detección está integrada en la generación Y el post-procesamiento. La escritura pasa por CÓMO se construye en cada nivel.

### El pipeline de 5 etapas

```
┌─────────────────────────────────────────────────────────────────────┐
│                      GHOST PROTOCOL PIPELINE                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──┐ │
│  │ STAGE 1  │──▶│ STAGE 2  │──▶│ STAGE 3  │──▶│ STAGE 4  │──▶│5 │ │
│  │ Profile  │   │ Pattern  │   │  40-Pt   │   │ Platform │   │  │ │
│  │ Intake   │   │ Inject   │   │   QA     │   │ Adapt    │   │  │ │
│  └──────────┘   └──────────┘   └────┬─────┘   └──────────┘   └──┘ │
│                                     │                               │
│                              FAIL? ◀┘                               │
│                                │                                    │
│                         ┌──────▼──────┐                             │
│                         │  Targeted   │                             │
│                         │  Revision   │──── Loop back to Stage 2    │
│                         └─────────────┘                             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Arquitectura

### Vista general del sistema

```
writing-agent/
├── src/
│   ├── cli.js                  # CLI entry point
│   ├── ghost.js                # Main orchestrator
│   ├── agents/
│   │   ├── profile-agent.js    # Stage 1: Content profiling & voice loading
│   │   ├── writer-agent.js     # Stage 2: Human pattern injection engine
│   │   ├── qa-agent.js         # Stage 3: 40-point QA scoring
│   │   ├── adapter-agent.js    # Stage 4: Platform adaptation
│   │   └── polish-agent.js     # Stage 5: Final human pass simulation
│   ├── checks/
│   │   ├── index.js            # Check runner & aggregator
│   │   ├── statistical.js      # Checks 1-7
│   │   ├── classifier.js       # Checks 8-12
│   │   ├── linguistic.js       # Checks 13-18
│   │   ├── watermark.js        # Checks 19-20
│   │   ├── scoring.js          # Checks 21-25
│   │   ├── bias.js             # Checks 26-28
│   │   ├── adversarial.js      # Checks 29-31
│   │   ├── infrastructure.js   # Checks 32-34
│   │   ├── evaluation.js       # Checks 35-37
│   │   └── governance.js       # Checks 38-40
│   ├── adapters/
│   ├── utils/
│   └── templates/
├── config/
├── docs/
├── examples/
├── tests/
├── scripts/
├── package.json
├── LICENSE
├── CONTRIBUTING.md
└── CHANGELOG.md
```

> **Nota:** Los nombres de clases de agentes hacen referencia a la taxonomía de agentes Disney de [googleadsagent.ai](https://googleadsagent.ai) para consistencia con el ecosistema existente de 25+ agentes.

**Puntos de integración:**

| Repo | Integración | Propósito |
|------|-------------|---------|
| `advertising-hub` | Writing Agent se registra como agente de contenido junto a los 25+ agentes existentes | Creación de contenido dentro del flujo de gestión publicitaria |
| `google-ads-mcp` | Writing Agent obtiene datos de rendimiento de campañas vía herramientas MCP | Métricas reales y datos de casos para contenido auténtico |
| `ContextOS` | Perfiles de voz, memoria de sesión e historial de contenido almacenados en ContextOS | Calibración de voz persistente entre sesiones |
| `intel-harvester` | La inteligencia de contenido competitivo alimenta el descubrimiento de temas | Ángulos originales que no existen en los datos de entrenamiento IA |
| `google-ads-audit-engine` | Los hallazgos de auditoría se convierten en puntos de prueba en el contenido | Datos específicos y verificables que los detectores no pueden señalar |

---

## Instalación

### Prerrequisitos

- Node.js 18+
- npm o yarn
- Una clave API de Anthropic (para Claude) O clave API de OpenAI (para GPT-4)

### Instalar

```bash
git clone https://github.com/itallstartedwithaidea/writing-agent.git
cd writing-agent
npm install
npm link
cp config/default.yaml config/local.yaml
```

---

## Inicio rápido

### Escribir un post de LinkedIn

```bash
ghost write --type linkedin --topic "Why most Google Ads accounts waste 40% of budget on branded search they'd get organically"
```

### Escribir un artículo de blog

```bash
ghost write --type blog --topic "The ROAS trap: why your client thinks they're winning while actually losing" --length 1500
```

### Escribir un comentario de Reddit

```bash
ghost write --type reddit-comment --context "Someone asked: What's the biggest Google Ads mistake you see?" --tone casual
```

### Ejecutar QA de detección en texto existente

```bash
ghost check --file my-article.md
ghost check --text "paste your text here"
ghost check --file my-article.md --detectors gptzero,pangram,originality
```

---

## Tipos de contenido

| Tipo | Flag CLI | Descripción | Longitud predeterminada |
|------|----------|-------------|---------------|
| Artículo de blog | `blog` | Contenido experto de formato largo para sitios/Substack | 1200 palabras |
| Post LinkedIn | `linkedin` | Liderazgo de pensamiento profesional, atrapante | 200 palabras |
| Post Reddit | `reddit` | Intercambio de conocimiento entre pares, voz comunitaria | 400 palabras |
| Comentario Reddit | `reddit-comment` | Respuesta directa, casual, específica | 150 palabras |
| Artículo Substack | `substack` | Estilo newsletter, personal, serial | 1500 palabras |
| Libro blanco | `whitepaper` | Basado en datos, autoritario, estructurado | 3000 palabras |
| Email | `email` | Directo, sin relleno, orientado a la acción | 150 palabras |
| Caption Instagram | `instagram` | Visual primero, personalidad al frente | 150 palabras |
| Post Facebook | `facebook` | Atractivo, compartible, comunitario | 200 palabras |
| X/Twitter | `twitter` | Contundente, opinado, listo para threads | 280 caracteres |
| Texto web | `website` | Orientado a conversión, claro, centrado en beneficios | 500 palabras |
| Respuesta | `reply` | Adaptado al contexto, con valor añadido | 100 palabras |

---

## El sistema QA de 40 puntos

Cada contenido pasa por 40 verificaciones mapeadas a vectores de detección conocidos. El contenido debe obtener **PASS** en todas las verificaciones estrictas y no más de 3 fallos suaves para publicarse.

| Bloque | Verificaciones | Qué detecta |
|-------|--------|-----------------|
| **A: Estadístico** | #1-7 | Perplejidad, burstiness, distribución de tokens, curvatura de log-probabilidad, perplejidad cruzada, novedad n-gram, entropía |
| **B: Clasificador** | #8-12 | Inicios con conjunción, uso de fragmentos, paréntesis, **varianza de longitud de párrafo** (v2), **control de tricolones** (v2) |
| **C: Lingüístico** | #13-18 | Lista negra de 200+ frases, diversidad léxica, varianza de legibilidad, variedad sintáctica, **detección de Q&A retórico** (v2), **detección de aperturas IA** (v2) |
| **D: Marca de agua** | #19-20 | Eliminación de marca de agua digital, higiene de metadatos |
| **E: Puntuación** | #21-25 | Puntuación de confianza objetivo, limpieza a nivel de oración, plagio, resistencia a humanizadores, autenticidad lingüística |
| **F: Sesgo** | #26-28 | Explotación de sesgo no nativo, patrones específicos del dominio, optimización de longitud |
| **G: Adversarial** | #29-31 | Diversidad de patrones, resistencia a traducción, consistencia multi-autor |
| **H: Infraestructura** | #32-34 | Validación multi-detector, normalización de texto plano, formateo nativo de plataforma |
| **I: Evaluación** | #35-37 | Benchmarking de terceros, explotación de FPR, asistido por IA vs. generado por IA |
| **J: Gobernanza** | #38-40 | Cumplimiento de divulgación, pista de auditoría, construcción a prueba de proveniencia |

---

## Investigación periodística (v2.0)

### Lo que hacen los escritores reales (que la IA no hace)

| Patrón | Escritura real | Escritura IA |
|---|---|---|
| **Longitud de párrafo** | 1-2 oraciones (noticias), varía enormemente (reportajes) | 3-5 oraciones, uniformidad sospechosa |
| **Longitud de oración** | Rango de 7 a 52 palabras en un mismo artículo | 15-25 palabras consistentemente |
| **Apertura** | Escena, hecho específico o lead periodístico | "En el mundo en constante evolución de hoy..." |
| **Transiciones** | Saltos abruptos, cortes de sección, "Pero." | "Dicho esto," "¿Qué significa todo esto?" |
| **Datos** | 15.2%, $36.8M, 0-de-5 en 23 posesiones | "aumento significativo," "los datos muestran" |
| **Metáforas** | Una y listo. Nunca más referenciada. | Una metáfora hilvanada en todo el texto |
| **Voz** | 2-3 momentos de personalidad por cada 800 palabras | Marcadores de personalidad en cada párrafo |
| **Finales** | Cita, hecho específico, o simplemente se detiene | Lista resumen o "¿Cuál es la conclusión?" |
| **Concesiones** | Incluye info que complica la tesis | Cada punto refuerza la tesis |
| **Atribución** | Expertos nombrados con títulos y roles | "Los expertos dicen," "Los líderes del sector coinciden" |

---

## Investigación y citas

Ghost Protocol está construido sobre investigación de más de 50 fuentes más el corpus periodístico v2. Las citas académicas completas están en `docs/wiki/09-research-and-citations.md`.

---

## Contribuir

Ver [CONTRIBUTING.md](CONTRIBUTING.md) para las directrices. Áreas clave donde se aceptan contribuciones:

- **Nuevos adaptadores de plataforma** (TikTok, Discord, Slack, etc.)
- **Plantillas de perfiles de voz** para diferentes industrias
- **Verificaciones QA adicionales** a medida que surgen nuevos métodos de detección
- **Integraciones de API de detectores** para nuevas herramientas de detección
- **Soporte de idiomas** más allá del inglés
- **Conjuntos de datos de benchmark** para pruebas

---

## Licencia

Licencia MIT. Ver [LICENSE](LICENSE) para detalles.

---

## Descargo de responsabilidad

Writing Agent está diseñado para ayudar a los escritores a producir contenido auténtico y de alta calidad. No está diseñado para facilitar la deshonestidad académica, el fraude o el engaño. El propósito de la herramienta es asegurar que la escritura asistida por IA mantenga la calidad, voz y autenticidad que los lectores esperan y merecen. Úselo responsablemente.

---

<p align="center">
  <strong>Creado por <a href="https://itallstartedwithaidea.com">It All Started With A Idea</a></strong><br>
  <em>Parte del ecosistema <a href="https://googleadsagent.ai">googleadsagent.ai</a></em>
</p>
