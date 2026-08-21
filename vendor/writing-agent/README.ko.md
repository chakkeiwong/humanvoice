# ✍️ Writing Agent

[English](README.md) | [Français](README.fr.md) | [Español](README.es.md) | [中文](README.zh.md) | [Nederlands](README.nl.md) | [Русский](README.ru.md) | [한국어](README.ko.md)

**탐지 불가능한 AI 글쓰기 에이전트 — CLI 도구 & 멀티 에이전트 프레임워크**
*Ghost Protocol 방법론 기반*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-green.svg)](https://nodejs.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

> **최고의 AI 생성 콘텐츠는 아무도 AI가 생성한 줄 모르는 콘텐츠입니다. 속여서가 아니라 — 진짜로 잘 쓰여서.**

Writing Agent는 오픈소스 CLI 도구이자 멀티 에이전트 프레임워크로, AI 탐지 시스템을 통과하도록 보정된 인간 수준의 글쓰기를 생산합니다. 50편 이상의 학술 논문, 상용 탐지기 문서, 탐지 벤치마킹 연구에서 역공학한 정보와 **Harvard Business Review, ESPN, CNN, Wall Street Journal, Yahoo Finance, Search Engine Land, Search Engine Journal의 40편 이상 기사에 대한 실제 저널리즘 분석**을 기반으로 구축되었습니다.

**이것은 휴먼화 도구가 아닙니다.** 휴먼화 도구는 저급한 AI 콘텐츠에 립스틱을 바릅니다. Writing Agent는 탐지기가 정확히 무엇을 왜 찾는지, 그리고 실제 기자들이 어떻게 글을 쓰는지를 바탕으로 — 처음부터 진정성 있는 인간 품질의 콘텐츠를 생성합니다.

### v2.0 신기능 (2026년 3월)

- **저널리즘 기반 인텔리전스** — HBR, ESPN, CNN, WSJ, Yahoo, SEL, SEJ의 40편 이상 기사를 분석하여 진정한 인간 글쓰기 패턴 추출
- **200+ 문구 블랙리스트** — 100개에서 200개 이상의 금지된 AI 스타일 문구로 확장 (단어 변형 포함)
- **후처리 엔진** — `humanizeContent()`가 프로그래밍 방식으로 AI 결론 패턴, 복합 형용사, 헤징 쌍, 균일한 단락 구조를 제거
- **8가지 AI 패턴 탐지** — 새로운 신호: AI 스타일 오프닝, 상투적 문구, 수사적 Q&A, 삼중 나열, 균일 단락, AI 결론, 대시 남용
- **강화된 QA 검사** — 단락 길이 분산, 삼중 나열 탐지, 수사적 Q&A 탐지, AI 오프닝 문장 탐지
- **시그니처 문구 제거** — 보이스 프로필에 과도하게 사용되는 "캐치프레이즈"가 더 이상 없음
- **안티 패턴 규칙** — 에세이 구조, 스포츠 비유 관통, 세 항목 목록, 논제-결론 패턴에 대한 명시적 규칙

---

## 목차

- [작동 방식](#작동-방식)
- [아키텍처](#아키텍처)
- [설치](#설치)
- [빠른 시작](#빠른-시작)
- [CLI 레퍼런스](#cli-레퍼런스)
- [콘텐츠 유형](#콘텐츠-유형)
- [40점 QA 시스템](#40점-qa-시스템)
- [플랫폼 어댑터](#플랫폼-어댑터)
- [보이스 프로필](#보이스-프로필)
- [설정](#설정)
- [Wiki & 예제](#wiki--예제)
- [연구 & 인용](#연구--인용)
- [기여](#기여)
- [라이선스](#라이선스)

---

## 작동 방식

Ghost Protocol v2는 네 가지 핵심 법칙으로 작동합니다:

1. **저널리즘 기반 패턴** — 모든 글은 실제 HBR, ESPN, CNN, WSJ, SEL 기사에서 추출한 글쓰기 패턴을 따릅니다. 실제 작가는 장면이나 사실로 시작하고, 비유를 한 번 사용하고 버리며, 단락 길이를 크게 변화시키고, 구체적인 내용으로 마무리합니다 — 요약이 아니라.
2. **AI 변장 없음** — 캐치프레이즈를 통한 "개성" 추가 대신, 시스템이 프로그래밍 방식으로 AI 스타일 패턴을 제거합니다. 200+ 블랙리스트 문구, 8개 구조적 AI 패턴 탐지기, 기업 용어를 제거하는 후처리 엔진.
3. **캐치프레이즈 없는 보이스** — 보이스 프로필은 구조적 습관(문장 길이 분포, 단락 패턴, 접속사 사용)을 정의하지, 시그니처 문구를 정의하지 않습니다. 실제 작가에게는 캐치프레이즈가 없습니다.
4. **보이지 않는 아키텍처** — 탐지 회피가 생성과 후처리 모두에 내장되어 있습니다. 글이 통과하는 이유는 모든 수준에서 어떻게 구성되었는가 때문입니다.

### 5단계 파이프라인

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

## 설치

### 사전 요구사항

- Node.js 18+
- npm 또는 yarn
- Anthropic API 키 (Claude용) 또는 OpenAI API 키 (GPT-4용)

### 설치

```bash
git clone https://github.com/itallstartedwithaidea/writing-agent.git
cd writing-agent
npm install
npm link
cp config/default.yaml config/local.yaml
```

---

## 빠른 시작

### LinkedIn 게시물 작성

```bash
ghost write --type linkedin --topic "Why most Google Ads accounts waste 40% of budget on branded search they'd get organically"
```

### 블로그 글 작성

```bash
ghost write --type blog --topic "The ROAS trap: why your client thinks they're winning while actually losing" --length 1500
```

### Reddit 댓글 작성

```bash
ghost write --type reddit-comment --context "Someone asked: What's the biggest Google Ads mistake you see?" --tone casual
```

### 기존 텍스트에 탐지 QA 실행

```bash
ghost check --file my-article.md
ghost check --text "paste your text here"
ghost check --file my-article.md --detectors gptzero,pangram,originality
```

---

## 콘텐츠 유형

| 유형 | CLI 플래그 | 설명 | 기본 길이 |
|------|----------|-------------|---------------|
| 블로그 글 | `blog` | 웹사이트/Substack용 장문 전문가 콘텐츠 | 1200 단어 |
| LinkedIn 게시물 | `linkedin` | 전문적 사고 리더십, 스크롤 멈추게 하는 | 200 단어 |
| Reddit 게시물 | `reddit` | 동료 수준 지식 공유, 커뮤니티 목소리 | 400 단어 |
| Reddit 댓글 | `reddit-comment` | 직접적 응답, 캐주얼, 구체적 | 150 단어 |
| Substack 기사 | `substack` | 뉴스레터 스타일, 개인적, 연재 | 1500 단어 |
| 백서 | `whitepaper` | 데이터 기반, 권위 있는, 구조화된 | 3000 단어 |
| 이메일 | `email` | 직접적, 군더더기 없는, 행동 지향 | 150 단어 |
| Instagram 캡션 | `instagram` | 비주얼 우선, 개성 전면 | 150 단어 |
| Facebook 게시물 | `facebook` | 참여 유도, 공유 가능, 커뮤니티 | 200 단어 |
| X/Twitter | `twitter` | 임팩트 있는, 의견 있는, 스레드 준비 | 280자 |
| 웹사이트 카피 | `website` | 전환 중심, 명확한, 혜택 기반 | 500 단어 |
| 답변 | `reply` | 컨텍스트에 맞는, 가치 추가 | 100 단어 |

---

## 40점 QA 시스템

모든 콘텐츠는 알려진 탐지 벡터에 매핑된 40개 검사를 통과합니다. 콘텐츠는 모든 하드 체크에서 **PASS**를 받고 소프트 실패가 3개 이하여야 출시됩니다.

| 블록 | 검사 | 대상 |
|-------|--------|-----------------|
| **A: 통계** | #1-7 | 퍼플렉시티, 버스트성, 토큰 분포, 로그 확률 곡률, 교차 퍼플렉시티, n-gram 신규성, 엔트로피 |
| **B: 분류기** | #8-12 | 접속사 시작, 단편 사용, 괄호 삽입, **단락 길이 분산** (v2), **삼중 나열 제어** (v2) |
| **C: 언어학** | #13-18 | 200+ 문구 블랙리스트, 어휘 다양성, 가독성 분산, 구문 다양성, **수사적 Q&A 탐지** (v2), **AI 오프닝 탐지** (v2) |
| **D: 워터마크** | #19-20 | 디지털 워터마크 제거, 메타데이터 위생 |
| **E: 스코어링** | #21-25 | 신뢰도 점수 타겟, 문장 수준 클린, 표절, 휴먼화 도구 저항, 언어 진정성 |
| **F: 편향** | #26-28 | 비원어민 편향 활용, 도메인 특정 패턴, 길이 최적화 |
| **G: 적대적** | #29-31 | 패턴 다양성, 번역 저항, 혼합 저자 일관성 |
| **H: 인프라** | #32-34 | 멀티 탐지기 검증, 일반 텍스트 정규화, 플랫폼 네이티브 포맷 |
| **I: 평가** | #35-37 | 제3자 벤치마킹, FPR 활용, AI 지원 vs. AI 생성 |
| **J: 거버넌스** | #38-40 | 공개 규정 준수, 감사 추적, 출처 증명 구성 |

---

## 저널리즘 연구 (v2.0)

### 실제 작가가 하는 것 (AI가 하지 않는 것)

| 패턴 | 실제 글쓰기 | AI 글쓰기 |
|---|---|---|
| **단락 길이** | 1-2 문장 (뉴스), 크게 변동 (피처) | 3-5 문장, 의심스러울 정도로 균일 |
| **문장 길이** | 한 기사 내 7-52 단어 범위 | 일관된 15-25 단어 |
| **시작** | 장면, 구체적 사실, 또는 뉴스 리드 | "오늘날 빠르게 변화하는 세계에서..." |
| **전환** | 갑작스러운 전환, 섹션 구분, "하지만." | "그렇긴 하지만," "그래서 이게 무슨 뜻일까요?" |
| **데이터** | 15.2%, $36.8M, 23번 공격 중 0-5 | "상당한 증가," "데이터가 보여주듯" |
| **비유** | 한 번 쓰고 끝. 다시 언급하지 않음. | 하나의 비유가 전체 글에 관통 |
| **목소리** | 800단어당 2-3개의 구체적 개성 순간 | 모든 단락에 개성 마커 |
| **결말** | 인용, 구체적 사실, 또는 그냥 멈춤 | 요약 목록 또는 "핵심 교훈은?" |

---

## 연구 & 인용

Ghost Protocol은 50개 이상의 출처와 v2 저널리즘 코퍼스 연구를 기반으로 구축되었습니다. 전체 학술 인용은 `docs/wiki/09-research-and-citations.md`에 있습니다.

---

## 기여

가이드라인은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참조하세요. 기여를 환영하는 주요 영역:

- **새로운 플랫폼 어댑터** (TikTok, Discord, Slack 등)
- **보이스 프로필 템플릿** — 다양한 업종용
- **추가 QA 검사** — 새로운 탐지 방법 등장에 따라
- **탐지기 API 통합** — 새로운 탐지 도구용
- **언어 지원** — 영어 외
- **벤치마크 데이터셋** — 테스트용

---

## 라이선스

MIT 라이선스. 자세한 내용은 [LICENSE](LICENSE)를 참조하세요.

---

## 면책 조항

Writing Agent는 작가가 진정성 있고 고품질의 콘텐츠를 생산하는 것을 돕기 위해 설계되었습니다. 학문적 부정행위, 사기 또는 기만을 촉진하기 위해 설계된 것이 아닙니다. 이 도구의 목적은 AI 보조 글쓰기가 독자가 기대하고 받을 자격이 있는 품질, 목소리, 진정성을 유지하도록 보장하는 것입니다. 책임감 있게 사용하세요.

---

<p align="center">
  <strong><a href="https://itallstartedwithaidea.com">It All Started With A Idea</a> 제작</strong><br>
  <em><a href="https://googleadsagent.ai">googleadsagent.ai</a> 에코시스템의 일부</em>
</p>
