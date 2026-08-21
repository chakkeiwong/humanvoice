# ✍️ Writing Agent

[English](README.md) | [Français](README.fr.md) | [Español](README.es.md) | [中文](README.zh.md) | [Nederlands](README.nl.md) | [Русский](README.ru.md) | [한국어](README.ko.md)

**Ondetecteerbare AI Writing Agent — CLI-tool & multi-agent framework**
*Aangedreven door de Ghost Protocol-methodologie*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-green.svg)](https://nodejs.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

> **De beste AI-gegenereerde content is content waarvan niemand weet dat het door AI is gegenereerd. Niet omdat het misleidt — maar omdat het echt goed is.**

Writing Agent is een open-source CLI-tool en multi-agent framework dat menswaardige schrijfkwaliteit produceert, gekalibreerd om AI-detectiesystemen te passeren. Gebouwd op reverse-engineered intelligence uit 50+ academische papers, commerciële detectordocumentatie, detectie-benchmarkstudies, en **real-world journalistieke analyse van 40+ artikelen uit Harvard Business Review, ESPN, CNN, Wall Street Journal, Yahoo Finance, Search Engine Land en Search Engine Journal**.

**Dit is GEEN humanizer-tool.** Humanizers nemen slechte AI-content en maken het op. Writing Agent genereert authentieke, menswaardige content vanaf nul — geïnformeerd door precies wat detectoren zoeken, waarom, en hoe echte journalisten daadwerkelijk schrijven.

### Nieuw in v2.0 (Maart 2026)

- **Journalistiek-geïnformeerde intelligence** — Analyse van 40+ artikelen uit HBR, ESPN, CNN, WSJ, Yahoo, SEL, SEJ om authentieke menselijke schrijfpatronen te extraheren
- **200+ zinswendingen blacklist** — Uitgebreid van 100 naar 200+ verboden AI-klinkende zinnen inclusief woordvarianten
- **Post-processing engine** — `humanizeContent()` verwijdert programmatisch AI-conclusiepatronen, samengestelde bijvoeglijke naamwoorden, hedging-paren en uniforme alineastructuren
- **8-patroon AI-detectie** — Nieuwe signalen: AI-achtige openingen, standaardzinnen, retorische Q&A, tricolons, uniforme alinea's, AI-conclusies, overmatig gebruik van gedachtestreepjes
- **Versterkte QA-controles** — Alinealengtevariatie, tricolon-detectie, retorische Q&A-detectie, AI-openingszindetectie
- **Geen handtekeningzinnen meer** — Stemprofielen hebben niet langer "catchphrases" die overmatig worden gebruikt
- **Anti-patroonregels** — Expliciete regels tegen essaystructuur, sportanalogie-threading, lijsten van drie, thesis-conclusiepatronen

---

## Inhoudsopgave

- [Hoe het werkt](#hoe-het-werkt)
- [Architectuur](#architectuur)
- [Installatie](#installatie)
- [Snel starten](#snel-starten)
- [CLI-referentie](#cli-referentie)
- [Contenttypes](#contenttypes)
- [Het 40-punts QA-systeem](#het-40-punts-qa-systeem)
- [Platformadapters](#platformadapters)
- [Stemprofielen](#stemprofielen)
- [Configuratie](#configuratie)
- [Wiki & voorbeelden](#wiki--voorbeelden)
- [Onderzoek & citaties](#onderzoek--citaties)
- [Bijdragen](#bijdragen)
- [Licentie](#licentie)

---

## Hoe het werkt

Ghost Protocol v2 werkt volgens vier kernwetten:

1. **Journalistiek-geïnformeerde patronen** — Elk stuk volgt schrijfpatronen geëxtraheerd uit echte HBR-, ESPN-, CNN-, WSJ- en SEL-artikelen. Echte schrijvers beginnen met een scène of feit, gebruiken metaforen één keer en laten ze los, variëren alinealengtes sterk, en eindigen met specifieke details — geen samenvattingen.
2. **Geen AI-vermomming** — In plaats van "persoonlijkheid" toe te voegen via catchphrases, verwijdert het systeem AI-klinkende patronen programmatisch. 200+ blacklisted zinnen, 8 structurele AI-patroondetectoren, en een post-processing engine die bedrijfsjargon elimineert.
3. **Stem zonder catchphrases** — Stemprofielen definiëren structurele gewoonten (zinslengteverdeling, alineapatronen, voegwoordgebruik), geen handtekeningzinnen. Echte schrijvers hebben geen catchphrases.
4. **Onzichtbare architectuur** — Detectie-ontwijking is ingebouwd in generatie ÉN post-processing. Het schrijven slaagt door HOE het op elk niveau is geconstrueerd.

### De 5-fase pipeline

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

## Installatie

### Vereisten

- Node.js 18+
- npm of yarn
- Een Anthropic API-sleutel (voor Claude) OF OpenAI API-sleutel (voor GPT-4)

### Installeren

```bash
git clone https://github.com/itallstartedwithaidea/writing-agent.git
cd writing-agent
npm install
npm link
cp config/default.yaml config/local.yaml
```

---

## Snel starten

### Een LinkedIn-post schrijven

```bash
ghost write --type linkedin --topic "Why most Google Ads accounts waste 40% of budget on branded search they'd get organically"
```

### Een blogpost schrijven

```bash
ghost write --type blog --topic "The ROAS trap: why your client thinks they're winning while actually losing" --length 1500
```

### Een Reddit-reactie schrijven

```bash
ghost write --type reddit-comment --context "Someone asked: What's the biggest Google Ads mistake you see?" --tone casual
```

### Detectie-QA op bestaande tekst uitvoeren

```bash
ghost check --file my-article.md
ghost check --text "paste your text here"
ghost check --file my-article.md --detectors gptzero,pangram,originality
```

---

## Contenttypes

| Type | CLI-flag | Beschrijving | Standaardlengte |
|------|----------|-------------|---------------|
| Blogpost | `blog` | Lange-vorm expertcontent voor websites/Substack | 1200 woorden |
| LinkedIn-post | `linkedin` | Professioneel thought leadership, scroll-stoppend | 200 woorden |
| Reddit-post | `reddit` | Kennisdeling op peerniveau, community-stem | 400 woorden |
| Reddit-reactie | `reddit-comment` | Directe reactie, casual, specifiek | 150 woorden |
| Substack-artikel | `substack` | Nieuwsbrief-stijl, persoonlijk, serieel | 1500 woorden |
| Witboek | `whitepaper` | Data-onderbouwd, gezaghebbend, gestructureerd | 3000 woorden |
| E-mail | `email` | Direct, geen opvulling, actiegericht | 150 woorden |
| Instagram-bijschrift | `instagram` | Visueel-eerst, persoonlijkheid voorop | 150 woorden |
| Facebook-bericht | `facebook` | Boeiend, deelbaar, community | 200 woorden |
| X/Twitter | `twitter` | Krachtig, opinionated, thread-ready | 280 tekens |
| Websitetekst | `website` | Conversiegericht, duidelijk, voordeel-geleid | 500 woorden |
| Antwoord | `reply` | Context-aangepast, waardetoevoegend | 100 woorden |

---

## Het 40-punts QA-systeem

Elk stuk content doorloopt 40 controles die zijn gekoppeld aan bekende detectievectoren. Content moet **PASS** scoren op alle harde controles en niet meer dan 3 zachte fails om te worden gepubliceerd.

| Blok | Controles | Wat het target |
|-------|--------|-----------------|
| **A: Statistisch** | #1-7 | Perplexiteit, burstiness, tokenverdeling, log-waarschijnlijkheidscurvatuur, kruisperplexiteit, n-gram nieuwheid, entropie |
| **B: Classificatie** | #8-12 | Voegwoordstarts, fragmentgebruik, tussenzinnen, **alinealengtevariatie** (v2), **tricolon-controle** (v2) |
| **C: Linguïstisch** | #13-18 | 200+ zinswending blacklist, lexicale diversiteit, leesbaarheidsvariantie, syntactische variëteit, **retorische Q&A-detectie** (v2), **AI-openingsdetectie** (v2) |
| **D: Watermerk** | #19-20 | Digitale watermerkverwijdering, metadata-hygiëne |
| **E: Scoring** | #21-25 | Betrouwbaarheidsscore-targeting, zinsniveau-zuiverheid, plagiaat, humanizer-weerstand, taal-authenticiteit |
| **F: Bias** | #26-28 | Niet-moedertaalbias-exploitatie, domeinspecifieke patronen, lengte-optimalisatie |
| **G: Adversarieel** | #29-31 | Patroondiversiteit, vertaalbestendig, gemengd-auteursconsistentie |
| **H: Infrastructuur** | #32-34 | Multi-detectorvalidatie, platte tekst-normalisatie, platformnative opmaak |
| **I: Evaluatie** | #35-37 | Derde-partij benchmarking, FPR-exploitatie, AI-geassisteerd vs. AI-gegenereerd |
| **J: Governance** | #38-40 | Openbaarmakingscompliance, audittrail, herkomstbewijs-constructie |

---

## Journalistiek onderzoek (v2.0)

### Wat echte schrijvers doen (wat AI niet doet)

| Patroon | Echt schrijven | AI-schrijven |
|---|---|---|
| **Alinealengte** | 1-2 zinnen (nieuws), varieert sterk (features) | 3-5 zinnen, verdacht uniform |
| **Zinslengte** | 7-52 woorden bereik binnen één artikel | 15-25 woorden consistent |
| **Opening** | Scène, specifiek feit, of nieuws-lede | "In de snel veranderende wereld van vandaag..." |
| **Overgangen** | Abrupte sprongen, sectie-onderbrekingen, "Maar." | "Dat gezegd hebbende," "Dus wat betekent dit?" |
| **Data** | 15,2%, $36,8M, 0-van-5 in 23 balbezit | "aanzienlijke toename," "de data toont" |
| **Metaforen** | Eén en klaar. Nooit meer gerefereerd. | Eén metafoor door het hele stuk |
| **Stem** | 2-3 specifieke persoonlijkheidsmomenten per 800 woorden | Persoonlijkheidsmarkers in elke alinea |
| **Einde** | Citaat, specifiek feit, of stopt gewoon | Samenvattingslijst of "Wat is de takeaway?" |

---

## Onderzoek & citaties

Ghost Protocol is gebouwd op onderzoek van 50+ bronnen plus het v2-journalistiekcorpus. Volledige academische citaties staan in `docs/wiki/09-research-and-citations.md`.

---

## Bijdragen

Zie [CONTRIBUTING.md](CONTRIBUTING.md) voor richtlijnen. Belangrijke gebieden waar bijdragen welkom zijn:

- **Nieuwe platformadapters** (TikTok, Discord, Slack, etc.)
- **Stemprofiel-templates** voor verschillende industrieën
- **Aanvullende QA-controles** naarmate nieuwe detectiemethoden opkomen
- **Detector API-integraties** voor nieuwe detectietools
- **Taalondersteuning** buiten het Engels
- **Benchmark-datasets** voor tests

---

## Licentie

MIT-licentie. Zie [LICENSE](LICENSE) voor details.

---

## Disclaimer

Writing Agent is ontworpen om schrijvers te helpen authentieke, hoogwaardige content te produceren. Het is niet ontworpen om academische oneerlijkheid, fraude of misleiding te faciliteren. Het doel van de tool is ervoor te zorgen dat AI-geassisteerd schrijven de kwaliteit, stem en authenticiteit behoudt die lezers verwachten en verdienen. Gebruik verantwoord.

---

<p align="center">
  <strong>Gebouwd door <a href="https://itallstartedwithaidea.com">It All Started With A Idea</a></strong><br>
  <em>Onderdeel van het <a href="https://googleadsagent.ai">googleadsagent.ai</a>-ecosysteem</em>
</p>
