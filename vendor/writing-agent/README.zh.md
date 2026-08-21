# ✍️ Writing Agent

[English](README.md) | [Français](README.fr.md) | [Español](README.es.md) | [中文](README.zh.md) | [Nederlands](README.nl.md) | [Русский](README.ru.md) | [한국어](README.ko.md)

**无法被检测的 AI 写作代理 — CLI 工具和多代理框架**
*由 Ghost Protocol 方法论驱动*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-green.svg)](https://nodejs.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

> **最好的 AI 生成内容是没人知道它是 AI 生成的内容。不是因为它欺骗了谁——而是因为它确实很好。**

Writing Agent 是一个开源 CLI 工具和多代理框架，生产经过校准的人类品质写作，能通过 AI 检测系统。基于对 50 多篇学术论文、商业检测器文档、检测基准研究的逆向工程情报构建，以及**对 Harvard Business Review、ESPN、CNN、Wall Street Journal、Yahoo Finance、Search Engine Land 和 Search Engine Journal 的 40 多篇文章的真实新闻分析**。

**这不是一个人性化工具。** 人性化工具把 AI 垃圾内容涂脂抹粉。Writing Agent 从零开始生成真实的人类品质内容——基于检测器究竟在找什么、为什么找，以及真正的记者实际上是如何写作的。

### v2.0 新功能（2026年3月）

- **新闻实践驱动的智能** — 分析了 40 多篇来自 HBR、ESPN、CNN、WSJ、Yahoo、SEL、SEJ 的文章，提取真实人类写作模式
- **200+ 短语黑名单** — 从 100 扩展到 200+ 个禁用的 AI 风格短语，包括词汇变体
- **后处理引擎** — `humanizeContent()` 以编程方式去除 AI 结论模式、复合形容词、对冲配对和统一段落结构
- **8 种 AI 模式检测** — 新信号：AI 风格开头、口头禅、修辞问答、三段排比、统一段落、AI 结论、破折号过度使用
- **强化的 QA 检查** — 段落长度方差、三段排比检测、修辞问答检测、AI 开头句检测
- **不再有标志性短语** — 语音配置不再有被过度使用的"口头禅"
- **反模式规则** — 明确规则反对论文结构、体育类比贯穿、三项列表、论点-结论模式

---

## 目录

- [工作原理](#工作原理)
- [架构](#架构)
- [安装](#安装)
- [快速开始](#快速开始)
- [CLI 参考](#cli-参考)
- [内容类型](#内容类型)
- [40 点 QA 系统](#40-点-qa-系统)
- [平台适配器](#平台适配器)
- [语音配置](#语音配置)
- [配置](#配置)
- [Wiki 和示例](#wiki-和示例)
- [研究与引用](#研究与引用)
- [贡献](#贡献)
- [许可证](#许可证)

---

## 工作原理

Ghost Protocol v2 基于四条核心法则运行：

1. **新闻实践驱动的模式** — 每篇内容都遵循从真实 HBR、ESPN、CNN、WSJ 和 SEL 文章中提取的写作模式。真正的作家以场景或事实开头，使用一次隐喻然后放弃，段落长度变化很大，以具体细节结尾——而不是总结。
2. **没有 AI 伪装** — 系统不是通过口头禅添加"个性"，而是以编程方式去除 AI 风格的模式。200+ 黑名单短语、8 个结构性 AI 模式检测器，以及一个去除企业废话的后处理引擎。
3. **没有口头禅的语音** — 语音配置定义的是结构性习惯（句子长度分布、段落模式、连词使用），而不是标志性短语。真正的作家没有口头禅。
4. **隐形架构** — 检测规避内置于生成和后处理中。写作之所以能通过检测，是因为它在每个层面上是如何构建的。

### 5 阶段流水线

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

## 安装

### 前置条件

- Node.js 18+
- npm 或 yarn
- Anthropic API 密钥（用于 Claude）或 OpenAI API 密钥（用于 GPT-4）

### 安装

```bash
git clone https://github.com/itallstartedwithaidea/writing-agent.git
cd writing-agent
npm install
npm link
cp config/default.yaml config/local.yaml
```

---

## 快速开始

### 撰写 LinkedIn 帖子

```bash
ghost write --type linkedin --topic "Why most Google Ads accounts waste 40% of budget on branded search they'd get organically"
```

### 撰写博客文章

```bash
ghost write --type blog --topic "The ROAS trap: why your client thinks they're winning while actually losing" --length 1500
```

### 撰写 Reddit 评论

```bash
ghost write --type reddit-comment --context "Someone asked: What's the biggest Google Ads mistake you see?" --tone casual
```

### 对现有文本运行检测 QA

```bash
ghost check --file my-article.md
ghost check --text "paste your text here"
ghost check --file my-article.md --detectors gptzero,pangram,originality
```

---

## 内容类型

| 类型 | CLI 标志 | 描述 | 默认长度 |
|------|----------|-------------|---------------|
| 博客文章 | `blog` | 面向网站/Substack 的长篇专家内容 | 1200 词 |
| LinkedIn 帖子 | `linkedin` | 专业思想领袖，吸引注意力 | 200 词 |
| Reddit 帖子 | `reddit` | 同行知识分享，社区声音 | 400 词 |
| Reddit 评论 | `reddit-comment` | 直接回复，随意，具体 | 150 词 |
| Substack 文章 | `substack` | 通讯风格，个人化，连载 | 1500 词 |
| 白皮书 | `whitepaper` | 数据驱动，权威，结构化 | 3000 词 |
| 电子邮件 | `email` | 直接，无废话，面向行动 | 150 词 |
| Instagram 标题 | `instagram` | 视觉优先，个性鲜明 | 150 词 |
| Facebook 帖子 | `facebook` | 有吸引力，可分享，社区化 | 200 词 |
| X/Twitter | `twitter` | 有力，有观点，适合线程 | 280 字符 |
| 网站文案 | `website` | 转化导向，清晰，以利益为导向 | 500 词 |
| 回复 | `reply` | 匹配上下文，有价值 | 100 词 |

---

## 40 点 QA 系统

每篇内容都要通过 40 项检查，映射到已知的检测向量。内容必须在所有严格检查中获得 **PASS**，且不超过 3 项软失败才能发布。

| 区块 | 检查 | 目标 |
|-------|--------|-----------------|
| **A: 统计** | #1-7 | 困惑度、突发性、令牌分布、对数概率曲率、交叉困惑度、n-gram 新颖性、熵 |
| **B: 分类器** | #8-12 | 连词开头、片段使用、括号旁白、**段落长度方差**（v2）、**三段排比控制**（v2） |
| **C: 语言学** | #13-18 | 200+ 短语黑名单、词汇多样性、可读性方差、句法多样性、**修辞问答检测**（v2）、**AI 开头检测**（v2） |
| **D: 水印** | #19-20 | 数字水印去除、元数据清洁 |
| **E: 评分** | #21-25 | 置信度评分目标、句子级清洁、抄袭、人性化工具抵抗、语言真实性 |
| **F: 偏差** | #26-28 | 非母语偏差利用、领域特定模式、长度优化 |
| **G: 对抗** | #29-31 | 模式多样性、翻译抵抗、多作者一致性 |
| **H: 基础设施** | #32-34 | 多检测器验证、纯文本标准化、平台原生格式 |
| **I: 评估** | #35-37 | 第三方基准测试、FPR 利用、AI 辅助 vs. AI 生成 |
| **J: 治理** | #38-40 | 披露合规、审计跟踪、来源证明构建 |

---

## 新闻研究（v2.0）

### 真正的作家做什么（而 AI 不做）

| 模式 | 真实写作 | AI 写作 |
|---|---|---|
| **段落长度** | 1-2 句（新闻），变化极大（特稿） | 3-5 句，可疑地统一 |
| **句子长度** | 同一篇文章中 7-52 词的范围 | 持续 15-25 词 |
| **开头** | 场景、具体事实或新闻导语 | "在当今快速发展的世界..." |
| **过渡** | 突然跳转、分节、"但是。" | "话虽如此，" "那么这意味着什么？" |
| **数据** | 15.2%、3680万美元、23次进攻中的0-5 | "显著增长"、"数据显示" |
| **隐喻** | 用一次就丢弃。不再提及。 | 一个隐喻贯穿全文 |
| **语气** | 每800词2-3个个性化时刻 | 每段都有个性标记 |
| **结尾** | 引言、具体事实，或直接结束 | 总结列表或"结论是什么？" |
| **让步** | 包含使论点复杂化的信息 | 每个要点都强化论点 |
| **引用** | 有姓名、头衔和角色的专家 | "专家说"、"行业领导者一致认为" |

---

## 研究与引用

Ghost Protocol 基于 50 多个来源和 v2 新闻语料库的研究构建。完整的学术引用请参见 `docs/wiki/09-research-and-citations.md`。

---

## 贡献

请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 了解指南。欢迎贡献的关键领域：

- **新平台适配器**（TikTok、Discord、Slack 等）
- **语音配置模板**，面向不同行业
- **额外的 QA 检查**，随着新检测方法的出现
- **检测器 API 集成**，面向新的检测工具
- **语言支持**，扩展到英语以外
- **基准数据集**，用于测试

---

## 许可证

MIT 许可证。详见 [LICENSE](LICENSE)。

---

## 免责声明

Writing Agent 旨在帮助作家创作真实、高质量的内容。它不是为了促进学术不诚实、欺诈或欺骗而设计的。该工具的目的是确保 AI 辅助写作保持读者期望和应得的质量、声音和真实性。请负责任地使用。

---

<p align="center">
  <strong>由 <a href="https://itallstartedwithaidea.com">It All Started With A Idea</a> 构建</strong><br>
  <em><a href="https://googleadsagent.ai">googleadsagent.ai</a> 生态系统的一部分</em>
</p>
