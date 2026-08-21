# ✍️ Writing Agent

[English](README.md) | [Français](README.fr.md) | [Español](README.es.md) | [中文](README.zh.md) | [Nederlands](README.nl.md) | [Русский](README.ru.md) | [한국어](README.ko.md)

**Agent d'écriture IA indétectable — Outil CLI et framework multi-agents**
*Propulsé par la méthodologie Ghost Protocol*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-green.svg)](https://nodejs.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

> **Le meilleur contenu généré par IA est celui que personne ne sait être généré par IA. Non pas parce qu'il trompe — mais parce qu'il est vraiment bon.**

Writing Agent est un outil CLI open-source et un framework multi-agents qui produit une écriture de qualité humaine calibrée pour passer les systèmes de détection IA. Construit sur du renseignement rétro-ingéniéré à partir de plus de 50 articles académiques, documentations de détecteurs commerciaux, études de benchmarking de détection, et **analyse journalistique réelle de plus de 40 articles de Harvard Business Review, ESPN, CNN, Wall Street Journal, Yahoo Finance, Search Engine Land et Search Engine Journal**.

**Ceci N'EST PAS un outil d'humanisation.** Les humaniseurs prennent du contenu IA médiocre et le maquillent. Writing Agent génère du contenu authentique de qualité humaine à partir de zéro — informé par ce que les détecteurs recherchent exactement, pourquoi, et comment les vrais journalistes écrivent réellement.

### Nouveautés v2.0 (Mars 2026)

- **Intelligence inspirée du journalisme** — Analyse de plus de 40 articles de HBR, ESPN, CNN, WSJ, Yahoo, SEL, SEJ pour extraire des patterns d'écriture humaine authentiques
- **Liste noire de 200+ phrases** — Élargie de 100 à 200+ phrases interdites à consonance IA incluant les variantes
- **Moteur de post-traitement** — `humanizeContent()` supprime programmatiquement les patterns de conclusion IA, adjectifs composés, paires d'atténuation et structures de paragraphes uniformes
- **Détection de 8 patterns IA** — Nouveaux signaux : ouvertures IA, phrases toutes faites, Q&R rhétoriques, tricolons, paragraphes uniformes, conclusions IA, abus de tirets
- **Contrôles QA renforcés** — Variance de longueur de paragraphe, détection de tricolons, détection de Q&R rhétorique, détection de phrases d'ouverture IA
- **Plus de phrases signatures** — Les profils de voix n'ont plus de « phrases fétiches » surexploitées
- **Règles anti-patterns** — Règles explicites contre la structure dissertative, le filage d'analogies sportives, les listes de trois, les patterns thèse-conclusion

---

## Table des matières

- [Comment ça marche](#comment-ça-marche)
- [Architecture](#architecture)
- [Installation](#installation)
- [Démarrage rapide](#démarrage-rapide)
- [Référence CLI](#référence-cli)
- [Types de contenu](#types-de-contenu)
- [Le système QA en 40 points](#le-système-qa-en-40-points)
- [Adaptateurs de plateforme](#adaptateurs-de-plateforme)
- [Profils de voix](#profils-de-voix)
- [Intégration avec les repos existants](#intégration-avec-les-repos-existants)
- [Configuration](#configuration)
- [Wiki et exemples](#wiki--exemples)
- [Recherche et citations](#recherche--citations)
- [Contribuer](#contribuer)
- [Licence](#licence)

---

## Comment ça marche

Ghost Protocol v2 fonctionne selon quatre lois fondamentales :

1. **Patterns inspirés du journalisme** — Chaque contenu suit des patterns d'écriture extraits de vrais articles HBR, ESPN, CNN, WSJ et SEL. Les vrais écrivains commencent par une scène ou un fait, utilisent les métaphores une fois puis les abandonnent, varient considérablement la longueur des paragraphes, et terminent sur des détails — pas des résumés.
2. **Pas de déguisement IA** — Au lieu d'ajouter de la « personnalité » via des phrases toutes faites, le système supprime les patterns à consonance IA programmatiquement. 200+ phrases en liste noire, 8 détecteurs de patterns structurels IA, et un moteur de post-traitement qui élimine le jargon corporate.
3. **Voix sans phrases fétiches** — Les profils de voix définissent des habitudes structurelles (distribution de longueur de phrases, patterns de paragraphes, usage de conjonctions), pas des phrases signatures. Les vrais écrivains n'ont pas de phrases fétiches.
4. **Architecture invisible** — L'évasion de détection est intégrée dans la génération ET le post-traitement. L'écriture passe grâce à la façon dont elle est construite à chaque niveau.

### Le pipeline en 5 étapes

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

## Architecture

### Vue d'ensemble du système

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
│   │   ├── statistical.js      # Checks 1-7: Perplexity, burstiness, entropy
│   │   ├── classifier.js       # Checks 8-12: Transformer & ensemble resistance
│   │   ├── linguistic.js       # Checks 13-18: Stylometry, lexical diversity
│   │   ├── watermark.js        # Checks 19-20: Watermark & metadata stripping
│   │   ├── scoring.js          # Checks 21-25: Confidence & sentence-level
│   │   ├── bias.js             # Checks 26-28: Bias exploitation
│   │   ├── adversarial.js      # Checks 29-31: Pattern diversity & evasion
│   │   ├── infrastructure.js   # Checks 32-34: Multi-detector & normalization
│   │   ├── evaluation.js       # Checks 35-37: Benchmarking & classification
│   │   └── governance.js       # Checks 38-40: Disclosure & provenance
│   ├── adapters/
│   │   ├── google-docs.js      # Google Docs integration (via API)
│   │   ├── word.js             # Microsoft Word / .docx output
│   │   ├── linkedin.js         # LinkedIn post formatter
│   │   ├── reddit.js           # Reddit post/comment formatter
│   │   ├── substack.js         # Substack article formatter
│   │   ├── instagram.js        # Instagram caption formatter
│   │   ├── facebook.js         # Facebook post formatter
│   │   ├── twitter.js          # X/Twitter formatter
│   │   ├── email.js            # Email formatter
│   │   └── markdown.js         # Generic markdown output
│   ├── utils/
│   │   ├── text-analysis.js    # Perplexity, burstiness, entropy calculations
│   │   ├── phrase-blacklist.js # AI phrase kill list
│   │   ├── normalizer.js       # Unicode/whitespace normalization
│   │   ├── sentence-tools.js   # Sentence splitting, length analysis
│   │   └── detector-api.js     # Multi-detector API client
│   └── templates/
│       ├── system-prompts/     # Per-content-type system prompts
│       └── voice-profiles/     # Voice profile configurations
├── config/
│   ├── default.yaml            # Default configuration
│   ├── voice-profiles.yaml     # Voice profile definitions
│   ├── phrase-blacklist.yaml   # AI phrase kill list (200+ phrases)
│   └── detector-config.yaml    # Detector API keys & thresholds
├── docs/
│   └── wiki/                   # Full wiki documentation
├── examples/
│   ├── outputs/                # Before/after examples for each content type
│   └── prompts/                # Example prompt configurations
├── tests/
├── scripts/
├── package.json
├── LICENSE
├── CONTRIBUTING.md
└── CHANGELOG.md
```

### Architecture des agents

Ghost Protocol utilise un **pipeline de 5 agents** où chaque agent a une responsabilité spécifique :

```
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT ORCHESTRATION                           │
│                                                                 │
│  ┌─────────────────┐                                           │
│  │  PROFILE AGENT   │  Classifies content type, loads voice    │
│  │  (Simba-class)   │  profile, sets perplexity/burstiness     │
│  └────────┬────────┘  targets, identifies platform constraints │
│           │                                                     │
│  ┌────────▼────────┐                                           │
│  │  WRITER AGENT    │  Generates content with human pattern    │
│  │  (Nemo-class)    │  injection at structural, sentence,      │
│  └────────┬────────┘  and word levels                          │
│           │                                                     │
│  ┌────────▼────────┐      ┌─────────────┐                     │
│  │   QA AGENT       │─────▶│  REVISION   │                     │
│  │  (Baymax-class)  │ FAIL │  LOOP       │──▶ Back to Writer   │
│  └────────┬────────┘      └─────────────┘                     │
│           │ PASS                                                │
│  ┌────────▼────────┐                                           │
│  │ ADAPTER AGENT    │  Formats for target platform             │
│  │  (Elsa-class)    │  (LinkedIn, Reddit, Docs, Word, etc.)   │
│  └────────┬────────┘                                           │
│           │                                                     │
│  ┌────────▼────────┐                                           │
│  │  POLISH AGENT    │  Final human pass simulation —           │
│  │  (Mowgli-class)  │  2-3 small "random" edits               │
│  └─────────────────┘                                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

> **Note :** Les noms de classes d'agents font référence à la taxonomie d'agents Disney de [googleadsagent.ai](https://googleadsagent.ai) pour la cohérence avec l'écosystème existant de 25+ agents.

### Connexion avec vos repos existants

```
┌──────────────────────────────────────────────────────────────────┐
│                 IT ALL STARTED WITH A IDEA                        │
│                    ECOSYSTEM MAP                                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │  writing-agent   │    │ advertising-hub   │                   │
│  │  (THIS REPO)      │◄──▶│ (14 platforms)    │                   │
│  │                   │    │ 25+ agents        │                   │
│  │  • Writing Agent  │    │ • Simba (Search)  │                   │
│  │  • QA Engine      │    │ • Nemo (Display)  │                   │
│  │  • Platform       │    │ • Elsa (Social)   │                   │
│  │    Adapters       │    │ • Baymax (Audit)  │                   │
│  └───────┬──────────┘    └────────┬─────────┘                   │
│          │                        │                              │
│          │    ┌───────────────────┘                              │
│          │    │                                                   │
│  ┌───────▼────▼─────┐    ┌──────────────────┐                   │
│  │ google-ads-mcp    │    │  ContextOS        │                   │
│  │ (23 MCP tools)    │    │  (Unified MCP     │                   │
│  │                   │    │   Context Layer)   │                   │
│  │ • Campaign data   │    │                   │                   │
│  │ • Ad copy context │    │ • Session memory  │                   │
│  │ • Performance     │    │ • Voice profiles  │                   │
│  │   metrics         │    │ • Content history │                   │
│  └──────────────────┘    └──────────────────┘                   │
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │ intel-harvester   │    │ google-ads-audit  │                   │
│  │ v2.1              │    │ engine (250-pt)   │                   │
│  │                   │    │                   │                   │
│  │ • Competitor      │    │ • Audit data for  │                   │
│  │   content intel   │    │   case studies    │                   │
│  │ • Topic discovery │    │ • Performance     │                   │
│  │ • Trend signals   │    │   proof points    │                   │
│  └──────────────────┘    └──────────────────┘                   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Points d'intégration :**

| Repo | Intégration | Objectif |
|------|-------------|---------|
| `advertising-hub` | Writing Agent s'inscrit comme agent de contenu aux côtés des 25+ agents existants | Création de contenu dans le workflow de gestion publicitaire |
| `google-ads-mcp` | Writing Agent récupère les données de performance des campagnes via les outils MCP | Métriques réelles et données de cas pour du contenu authentique |
| `ContextOS` | Profils de voix, mémoire de session et historique de contenu stockés dans ContextOS | Calibration vocale persistante entre les sessions |
| `intel-harvester` | L'intelligence de contenu concurrentiel alimente la découverte de sujets | Angles originaux absents des données d'entraînement IA |
| `google-ads-audit-engine` | Les résultats d'audit deviennent des preuves dans le contenu | Données spécifiques et vérifiables que les détecteurs ne peuvent pas signaler |

---

## Installation

### Prérequis

- Node.js 18+
- npm ou yarn
- Une clé API Anthropic (pour Claude) OU une clé API OpenAI (pour GPT-4)

### Installer

```bash
git clone https://github.com/itallstartedwithaidea/writing-agent.git
cd writing-agent
npm install
npm link
cp config/default.yaml config/local.yaml
```

### Clés API (optionnel mais recommandé)

Pour le pipeline de QA multi-détecteurs, vous aurez besoin de clés API pour :

```yaml
# config/local.yaml
detectors:
  gptzero:
    api_key: "your-gptzero-api-key"
    threshold: 30
  pangram:
    api_key: "your-pangram-api-key"
    threshold: 30
  originality:
    api_key: "your-originality-api-key"
    threshold: 30

llm:
  provider: "anthropic"
  api_key: "your-api-key"
  model: "claude-sonnet-4-20250514"
```

---

## Démarrage rapide

### Écrire un post LinkedIn

```bash
ghost write --type linkedin --topic "Why most Google Ads accounts waste 40% of budget on branded search they'd get organically"
```

### Écrire un article de blog

```bash
ghost write --type blog --topic "The ROAS trap: why your client thinks they're winning while actually losing" --length 1500
```

### Écrire un commentaire Reddit

```bash
ghost write --type reddit-comment --context "Someone asked: What's the biggest Google Ads mistake you see?" --tone casual
```

### Écrire un e-mail

```bash
ghost write --type email --to "client" --topic "Q1 performance summary and recommended budget reallocation"
```

### Lancer un contrôle QA sur un texte existant

```bash
ghost check --file my-article.md
ghost check --text "paste your text here"
ghost check --file my-article.md --detectors gptzero,pangram,originality
```

### Exporter dans différents formats

```bash
ghost write --type blog --topic "..." --output docx
ghost write --type blog --topic "..." --output gdocs
ghost write --type blog --topic "..." --output markdown
ghost write --type blog --topic "..." --output html
```

---

## Référence CLI

### `ghost write`

Génère du contenu via le pipeline complet en 5 étapes.

```
Usage: ghost write [options]

Options:
  --type <type>          Content type (required)
                         blog, linkedin, reddit, reddit-comment, substack,
                         whitepaper, email, instagram, facebook, twitter,
                         website, reply
  --topic <topic>        Topic or brief for the content
  --context <context>    Additional context (parent post for replies, etc.)
  --tone <tone>          Override voice tone (casual, professional, technical, persuasive)
  --length <words>       Target word count (default varies by type)
  --voice <profile>      Voice profile to use (default: "john-williams")
  --output <format>      Output format: markdown, docx, gdocs, html, txt (default: markdown)
  --output-file <path>   Save to specific file path
  --no-qa                Skip QA checks (not recommended)
  --no-detect            Skip multi-detector validation
  --verbose              Show all QA check results
  --dry-run              Show plan without generating content
```

### `ghost check`

Lance le système QA en 40 points sur un texte existant.

```
Usage: ghost check [options]

Options:
  --file <path>          Path to text file to check
  --text <text>          Inline text to check
  --detectors <list>     Comma-separated detector list (default: all configured)
  --report <format>      Report format: summary, detailed, json (default: summary)
  --fix                  Auto-fix detected issues and output revised version
  --output-file <path>   Save report to file
```

### `ghost benchmark`

Lance le contenu contre plusieurs détecteurs et génère un rapport de comparaison.

```
Usage: ghost benchmark [options]

Options:
  --file <path>          Content file to benchmark
  --dir <path>           Directory of files to benchmark
  --detectors <list>     Detectors to use (default: all)
  --output <format>      json, csv, markdown (default: markdown)
```

### `ghost calibrate`

Calibre les seuils de détection pour un type de contenu ou une voix spécifique.

```
Usage: ghost calibrate [options]

Options:
  --type <type>          Content type to calibrate
  --voice <profile>      Voice profile to calibrate
  --samples <n>          Number of samples to generate (default: 20)
```

### `ghost profile`

Gère les profils de voix.

```
Usage: ghost profile [command]

Commands:
  list                   List all voice profiles
  show <name>            Show profile details
  create <name>          Create new profile (interactive)
  import <file>          Import profile from writing samples
  export <name> <file>   Export profile to file
```

---

## Types de contenu

| Type | Flag CLI | Description | Longueur par défaut |
|------|----------|-------------|---------------|
| Article de blog | `blog` | Contenu expert long format pour sites/Substack | 1200 mots |
| Post LinkedIn | `linkedin` | Leadership intellectuel professionnel, accrocheur | 200 mots |
| Post Reddit | `reddit` | Partage de connaissances entre pairs, voix communautaire | 400 mots |
| Commentaire Reddit | `reddit-comment` | Réponse directe, décontractée, spécifique | 150 mots |
| Article Substack | `substack` | Style newsletter, personnel, en série | 1500 mots |
| Livre blanc | `whitepaper` | Basé sur les données, autoritaire, structuré | 3000 mots |
| E-mail | `email` | Direct, sans fioritures, orienté action | 150 mots |
| Légende Instagram | `instagram` | Visuel d'abord, personnalité affirmée | 150 mots |
| Post Facebook | `facebook` | Engageant, partageable, communautaire | 200 mots |
| X/Twitter | `twitter` | Percutant, opinioné, prêt pour les threads | 280 caractères |
| Texte de site web | `website` | Orienté conversion, clair, axé bénéfices | 500 mots |
| Réponse | `reply` | Adapté au contexte, à valeur ajoutée | 100 mots |

Chaque type de contenu dispose d'un playbook dédié dans `docs/wiki/04-content-type-playbooks.md` avec des cibles de voix, des templates de structure et une calibration perplexité/burstiness.

---

## Le système QA en 40 points

Chaque contenu passe par 40 vérifications liées à des vecteurs de détection connus. Le contenu doit obtenir un **PASS** sur tous les contrôles stricts et pas plus de 3 échecs souples pour être publié.

### Blocs de vérification

| Bloc | Vérifications | Ce qu'il cible |
|-------|--------|-----------------|
| **A : Statistique** | #1-7 | Perplexité, burstiness, distribution de tokens, courbure de log-probabilité, perplexité croisée, nouveauté n-gram, entropie |
| **B : Classifieur** | #8-12 | Débuts par conjonction, usage de fragments, parenthèses, **variance de longueur de paragraphe** (v2), **contrôle de tricolons** (v2) |
| **C : Linguistique** | #13-18 | Liste noire de 200+ phrases, diversité lexicale, variance de lisibilité, variété syntaxique, **détection de Q&R rhétorique** (v2), **détection d'ouvertures IA** (v2) |
| **D : Filigrane** | #19-20 | Suppression de filigrane numérique, hygiène des métadonnées |
| **E : Scoring** | #21-25 | Ciblage de score de confiance, propreté au niveau phrase, plagiat, résistance aux humaniseurs, authenticité linguistique |
| **F : Biais** | #26-28 | Exploitation de biais non natif, patterns spécifiques au domaine, optimisation de longueur |
| **G : Adversarial** | #29-31 | Diversité de patterns, résistance à la traduction, cohérence multi-auteur |
| **H : Infrastructure** | #32-34 | Validation multi-détecteurs, normalisation texte brut, formatage natif de plateforme |
| **I : Évaluation** | #35-37 | Benchmarking tiers, exploitation du FPR, assisté par IA vs. généré par IA |
| **J : Gouvernance** | #38-40 | Conformité de divulgation, piste d'audit, construction à preuve de provenance |

Documentation complète : `docs/wiki/03-the-40-checks-explained.md`

---

## Adaptateurs de plateforme

Les adaptateurs formatent la sortie pour chaque destination de publication :

### Google Docs

```bash
ghost write --type blog --output gdocs --gdocs-id "your-doc-id"
```

Nécessite des identifiants API Google Docs dans la configuration. Crée ou ajoute à un Google Doc avec un formatage approprié (titres, gras, liens).

### Microsoft Word

```bash
ghost write --type whitepaper --output docx --output-file report.docx
```

Génère un fichier .docx formaté avec titres, styles, table des matières et mise en page professionnelle.

### Plateformes sociales

```bash
ghost write --type linkedin --topic "..."
ghost write --type reddit --topic "..."
ghost write --type instagram --topic "..."
```

### Publication directe (bientôt)

Adaptateurs prévus pour la publication directe via les API des plateformes :
- API LinkedIn (publication directe)
- API Reddit (publication/commentaire direct)
- API REST WordPress
- API Substack
- Intégration Buffer/Hootsuite

---

## Profils de voix

Les profils de voix définissent COMMENT l'agent écrit. Ils sont stockés dans `config/voice-profiles.yaml`.

### Profil par défaut : John Williams

```yaml
john-williams:
  name: "John Williams"
  background: "15+ year paid media veteran, Google Ads specialist, football coach"
  tone_anchors:
    - direct and opinionated
    - speaks from specific experience
    - uses coaching/football analogies
    - comfortable with profanity when it fits
    - mixes technical depth with accessibility
  vocabulary:
    domain_terms: ["ROAS", "PMax", "SQOS", "brand vs non-brand", "impression share"]
    signature_phrases: ["here's the thing", "I've seen this blow up at"]
    avoid: ["synergy", "leverage", "holistic", "paradigm"]
  structural_habits:
    starts_with_conjunctions: true
    uses_fragments: true
    parenthetical_asides: frequent
    average_sentence_length: 16
    sentence_length_stdev: 9
  perplexity_target: 30-45
  burstiness_target: "high"
```

### Créer des profils personnalisés

```bash
ghost profile create "agency-voice"
ghost profile import --samples ./my-writing-samples/ --name "my-natural-voice"
```

L'importateur de profils analyse votre écriture existante pour extraire votre empreinte stylométrique naturelle : distribution de longueur de phrases, préférences de vocabulaire, habitudes structurelles et patterns de ton.

---

## Configuration

### `config/default.yaml`

```yaml
version: "2.0.0"

llm:
  provider: "anthropic"
  model: "claude-sonnet-4-20250514"
  max_tokens: 4096
  temperature: 0.85

qa:
  enabled: true
  max_revision_loops: 3
  hard_fail_threshold: 0
  soft_fail_threshold: 3

detectors:
  enabled: true
  require_all_pass: true
  max_ai_probability: 30
  providers:
    gptzero:
      enabled: true
      threshold: 30
    pangram:
      enabled: true
      threshold: 30
    originality:
      enabled: false
      threshold: 30

content:
  default_voice: "john-williams"
  default_output: "markdown"

phrases:
  blacklist_file: "config/phrase-blacklist.yaml"
  zero_tolerance: true
```

---

## Wiki et exemples

### Pages Wiki

Le wiki complet est dans `docs/wiki/` :

| Page | Contenu |
|------|----------|
| [01 - Démarrage](docs/wiki/01-getting-started.md) | Installation, premier lancement, configuration de base |
| [02 - Architecture en détail](docs/wiki/02-architecture-deep-dive.md) | Pipeline en 5 étapes, rôles des agents, flux de données |
| [03 - Les 40 vérifications expliquées](docs/wiki/03-the-40-checks-explained.md) | Chaque vérification avec vecteur de détection, contre-mesure et code |
| [04 - Playbooks par type de contenu](docs/wiki/04-content-type-playbooks.md) | Voix, structure et cibles de calibration par type |
| [05 - Profils de voix](docs/wiki/05-voice-profiles.md) | Création, importation et réglage des profils de voix |
| [06 - Adaptateurs de plateforme](docs/wiki/06-platform-adapters.md) | Google Docs, Word, intégration de plateformes sociales |
| [07 - Guide d'intégration](docs/wiki/07-integration-guide.md) | Connexion à advertising-hub, ContextOS, serveurs MCP |
| [08 - Exemples et sorties](docs/wiki/08-examples-and-outputs.md) | Avant/après pour chaque type de contenu avec scores de détection |
| [09 - Recherche et citations](docs/wiki/09-research-and-citations.md) | Toutes les 50+ sources avec citations académiques complètes |
| [10 - Dépannage](docs/wiki/10-troubleshooting.md) | Problèmes courants, mises à jour des détecteurs, calibration |

---

## Recherche journalistique (v2.0)

Ghost Protocol v2 est basé sur l'analyse de plus de 40 articles réels de publications majeures. Découvertes clés qui ont façonné le moteur v2 :

### Ce que font les vrais écrivains (que l'IA ne fait pas)

| Pattern | Écriture réelle | Écriture IA |
|---|---|---|
| **Longueur de paragraphe** | 1-2 phrases (news), varie énormément (features) | 3-5 phrases, uniformité suspecte |
| **Longueur de phrase** | Plage de 7 à 52 mots dans un même article | 15-25 mots de façon constante |
| **Ouverture** | Scène, fait précis ou accroche journalistique | « Dans un monde en constante évolution... » |
| **Transitions** | Sauts abrupts, coupures de section, « Mais. » | « Cela dit, » « Que signifie tout cela ? » |
| **Données** | 15,2%, 36,8 M$, 0 sur 5 en 23 possessions | « augmentation significative », « les données montrent » |
| **Métaphores** | Une seule, puis abandonnée. Plus jamais référencée. | Une métaphore filée dans tout le texte |
| **Voix** | 2-3 moments de personnalité pour 800 mots | Marqueurs de personnalité à chaque paragraphe |
| **Fins** | Citation, fait précis, ou simplement s'arrête | Liste récapitulative ou « Quel est le message ? » |
| **Concessions** | Inclut des infos qui compliquent la thèse | Chaque point renforce la thèse |
| **Attribution** | Experts nommés avec titres et rôles | « Les experts disent, » « Les leaders du secteur s'accordent » |

### Sources analysées

- **Harvard Business Review** — Patterns d'ouverture, tension avant résolution, phrases pivots d'un mot
- **Harvard Gazette** — Voix basée sur les sources, cadrage académique sans jargon, deux-points avant la surprise
- **ESPN (Bill Barnwell)** — Oscillation radicale de longueur de phrase, preuve d'abord-conclusion ensuite, méthodologie de graphiques intégrés
- **CNN Business** — Structure de lede agence de presse, chargement de contexte par apposition, attribution honnête de l'incertitude
- **Yahoo Finance / Motley Fool** — Structure mise en place-surprise, données financières précises comme narrative
- **Search Engine Land** — Résumés orientés action, noms de produits spécifiques, résultats positifs/négatifs équilibrés
- **Search Engine Journal** — Titres fonctionnels, voix de praticien, métriques spécifiques intégrées

---

## Recherche et citations

Ghost Protocol est construit sur la recherche de plus de 50 sources plus le corpus journalistique v2. Les citations académiques complètes se trouvent dans `docs/wiki/09-research-and-citations.md`.

### Articles académiques clés

1. **Mitchell, E., Lee, Y., Khazatsky, A., Manning, C.D., & Finn, C.** (2023). DetectGPT: Zero-Shot Machine-Generated Text Detection using Probability Curvature. *ICML 2023*. [arXiv:2301.11305](https://arxiv.org/abs/2301.11305)

2. **Bao, G., Zhao, Y., Teng, Z., Yang, L., & Zhang, Y.** (2023). Fast-DetectGPT: Efficient Zero-Shot Detection of Machine-Generated Text via Conditional Probability Curvature. *ICLR 2024*. [arXiv:2310.05130](https://arxiv.org/abs/2310.05130)

3. **Liang, W., Yuksekgonul, M., Mao, Y., Wu, E., & Zou, J.** (2023). GPT Detectors are Biased Against Non-Native English Writers. *Patterns, 4(7)*. [arXiv:2304.02819](https://arxiv.org/abs/2304.02819)

4. **Hans, A., Schwarzschild, A., Cheber, V., et al.** (2024). Spotting LLMs With Binoculars: Zero-Shot Detection of Machine-Generated Text. *ICML 2024*. [arXiv:2401.12070](https://arxiv.org/abs/2401.12070)

5. **Mustapha, I.K., Osakue, A., & Odiakaose, K.** (2024). StyloAI: Distinguishing AI-Generated Content with Stylometric Analysis. *arXiv*. [arXiv:2405.10129](https://arxiv.org/abs/2405.10129)

### Références d'outils commerciaux

- GPTZero — [gptzero.me](https://gptzero.me) — Méthodologie perplexité/burstiness
- Pangram Labs — [pangram.com](https://pangram.com) — Détection par deep learning
- Grammarly AI Detector — [grammarly.com/ai-detector](https://grammarly.com/ai-detector) — #1 au benchmark RAID
- Winston AI — [gowinston.ai](https://gowinston.ai) — Détection multilingue
- Originality.ai — [originality.ai](https://originality.ai) — Détection combinée IA + plagiat
- QuillBot AI Detector — [quillbot.com](https://quillbot.com) — Distinction IA-généré vs IA-assisté
- Google SynthID — [ai.google.dev/responsible/docs/safeguards/synthid](https://ai.google.dev/responsible/docs/safeguards/synthid) — Filigranage de texte open-source

---

## Contribuer

Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour les directives. Domaines clés où les contributions sont les bienvenues :

- **Nouveaux adaptateurs de plateforme** (TikTok, Discord, Slack, etc.)
- **Templates de profils de voix** pour différentes industries
- **Vérifications QA supplémentaires** à mesure que de nouvelles méthodes de détection émergent
- **Intégrations API de détecteurs** pour de nouveaux outils de détection
- **Support linguistique** au-delà de l'anglais
- **Jeux de données de benchmark** pour les tests

---

## Licence

Licence MIT. Voir [LICENSE](LICENSE) pour les détails.

---

## Avertissement

Writing Agent est conçu pour aider les écrivains à produire du contenu authentique et de haute qualité. Il n'est pas conçu pour faciliter la malhonnêteté académique, la fraude ou la tromperie. L'objectif de l'outil est de garantir que l'écriture assistée par IA maintient la qualité, la voix et l'authenticité que les lecteurs attendent et méritent. Utilisez-le de manière responsable.

---

<p align="center">
  <strong>Créé par <a href="https://itallstartedwithaidea.com">It All Started With A Idea</a></strong><br>
  <em>Fait partie de l'écosystème <a href="https://googleadsagent.ai">googleadsagent.ai</a></em>
</p>
