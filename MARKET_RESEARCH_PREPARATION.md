# Market Research (Brand Strategy Hub) — PREPARATION.md

**Статус:** Preparation stage — заполняется до кода. Ничего не реализовано.
**Владелец продукта:** vlad@bluebeeweb.com
**Дата подготовки:** 2026-08-17, v0.1
**Vikunja:** #1867 (project *BBW Imperal Apps*), родитель #1846
**Sibling docs:** `MARKET_RESEARCH_PLAN.md` (тот же репозиторий — исходный концепт-черновик, эта заметка формализует его по стандарту `APP_PREPARATION_STANDARD.md`) · `sales-strategy-hub-plan.md` (соседний, но отдельный концепт — sales-side prospecting/CRM, НЕ здесь)
**Почему сейчас:** разбор кейса лидогенерации g4s.md (2026-08-17) показал, что `run_gap_analysis` и `run_swot_analysis` в Brand Strategy Hub реагируют только на данные, уже лежащие в сторе (свой профиль + сегмент) — весь реальный рыночный контекст (фрагментация рынка, реальные конкуренты, кто и как ищет подрядчиков в Молдове) пришлось собирать вручную через `web_search` вне приложения. Это системный пробел, не разовая случайность — см. заметку "G4S — лиды: разбор рынка и план лидогенерации".

---

## 1. Паспорт приложения

**Market Research** — не новое приложение, а новая capability внутри существующего **Brand Strategy Hub**. Даёт бренд-команде управляемый, инициируемый по запросу срез реального рынка (ландшафт, фрагментация, кандидаты в конкуренты, источники) и версионирует его так же, как уже версионируются `SWOTResult`/`GapAnalysisResult` — current + superseded.

Владелец продукта: vlad@bluebeeweb.com. Связанное событие: кейс g4s.md стал первым живым доказательством пробела; нет отдельного pilot — это расширение уже live-приложения.

## 2. Проблема в человеческих словах

Когда **владелец бренда или маркетинг-стратег** сталкивается с **задачей понять реальное положение бренда на рынке (для SWOT, gap-анализа или go-to-market плана)**, ему приходится **вручную идти в web_search, искать конкурентов, читать сайты, компилировать находки в чате — вне какого-либо приложения**, из-за чего **эта работа не сохраняется как структурированные данные, не воспроизводима, не видна другим участникам команды и не питает существующие инструменты `run_gap_analysis`/`run_swot_analysis`, которые остаются слепы к реальному рынку**.

Существующий Brand Strategy Hub эту боль не закрывает: `add_brand_competitor`/`list_brand_competitors` — это форма ручной записи (кто-то должен сначала сам найти конкурента во внешнем мире), а не инструмент обнаружения.

## 3. Пользователи, роли и права

| Роль | Job to be done | Данные | Права |
|---|---|---|---|
| Владелец бренда (VBS owner/editor — переиспользуем роли, уже существующие в Brand Strategy Hub) | Запустить рыночный срез перед стратегической сессией; решить, какие кандидаты реально конкуренты | Профиль бренда (industry/geography), результат снапшота | Может запускать `run_market_research`, может промоутить кандидата в `add_brand_competitor` |
| Reviewer (уже существующая VBS-роль) | Свериться с источниками снапшота перед тем, как решение бренда опирается на него | Снапшот целиком, включая sourcing trail | Может читать, не может запускать новый research или промоутить конкурента (только owner/editor) |
| Viewer | Понять текущий рыночный контекст бренда | Только текущий (`is_current=True`) снапшот | Read-only |

**Критерий:** роли переиспользуют существующую ролевую модель VBS (owner/editor/reviewer/viewer из `set_brand_membership`), не вводят новую систему прав — это одна и та же приватная workspace-модель.

## 4. Сценарии и точки решения человека

**Основной сценарий:**
```
триггер: стратег готовится к SWOT/gap-анализу или go-to-market плану для бренда
  → действие человека: вызывает run_market_research(brand_id, ...)
  → действие приложения: web_search + read_url по industry/geography бренда,
    пишет черновой MarketResearchSnapshot (candidate competitors, market notes, sourcing trail)
  → review/approval человека: владелец бренда просматривает кандидатов,
    решает, кого промоутить в add_brand_competitor (по одному или пакетно)
  → результат: реальные конкуренты зафиксированы в tracked competitors,
    market snapshot доступен как контекст для run_gap_analysis/run_swot_analysis
```

- **Happy path:** запрос → снапшот с кандидатами → человек промоутит 2-3 реальных → SWOT/gap-анализ теперь видят live market-контекст.
- **Missing/error path:** `web_search`/`read_url` не находят релевантных источников (нишевый рынок, нет описания industry на профиле) → снапшот сохраняется с пустым/частичным candidate-списком и явной пометкой "insufficient market signal", не выдумывает конкурентов.
- **Blocked state:** бренд-профиль не имеет заполненного `industry`/geography-контекста → `run_market_research` отказывает с понятной ошибкой ("заполните industry в профиле бренда сначала"), не запускает поиск вслепую.
- **Recovery path:** человек дозаполняет профиль (`update_brand_profile`) → повторный вызов `run_market_research` работает.
- **Точка, где решение остаётся за человеком:** промоушен кандидата в `add_brand_competitor` — приложение НИКОГДА не делает это автоматически (тот же human-in-the-loop принцип, что у VBS evidence review).

**Критерий:** сценарий уже прогнан на фиктивных данных — это буквально то, что произошло в кейсе g4s.md вручную (ROMVENT/Amexpert/ClimatLux/vent.md как кандидаты, вручную промоутнутые через `add_site_competitor`/`add_brand_competitor`).

## 5. Ценность и измеримый результат

- **Стратег:** не уходит из Brand Strategy Hub в чат/браузер для рыночного контекста — сбор и хранение остаются в одном инструменте.
- **Reviewer/owner:** видит sourcing trail (какие запросы/URL легли в основу) — может проверить, а не слепо доверять.
- **SWOT/gap-анализ:** становится грамотнее — опирается на реальный рынок, а не только на самоописание бренда.

**Измеримые критерии успеха:**
1. Доля новых SWOT/gap-анализов, у которых на момент запуска существует `is_current=True` `MarketResearchSnapshot` для бренда.
2. Доля кандидатов в снапшоте, реально промоутнутых в tracked competitors (сигнал качества поиска — если 0%, значит поиск нерелевантен).
3. Время от запроса `run_market_research` до готового снапшота (не должно требовать нескольких минут ручной работы стратега, как это было в кейсе g4s.md).
4. Число брендов, где `run_market_research` вызван хотя бы раз в течение 3 месяцев после релиза.

**Неуспех:** если после первого P0-среза кандидаты в снапшотах систематически нерелевантны (промоушен близок к 0%, стратеги возвращаются к ручному `web_search`) — сигнал, что grounding (industry/geography) недостаточен, и P0 нужно пересмотреть до расширения.

## 6. Границы: делает / не делает

**Входит в P0:**
- `run_market_research(brand_id)` — on-demand, callable, НЕ scheduled job.
- Пишет `MarketResearchSnapshot` (candidate competitors, market notes, sourcing trail), current/superseded версионирование как у SWOT.
- Человек промоутит кандидатов вручную через уже существующий `add_brand_competitor`.

**Не входит (сознательно, см. non-goals в `MARKET_RESEARCH_PLAN.md`):**
- НЕ standing/scheduled мониторинг рынка — только callable по запросу.
- НЕ tender/procurement scraper — явное решение вниз по приоритету (см. раздел "Tender monitoring — decision" в `MARKET_RESEARCH_PLAN.md`); если тендер всплывёт в реальной работе — обрабатывается вручную как обычная задача/лид.
- НЕ lead-база и не CRM — это зона Sales Strategy Hub (отдельный концепт), приложения должны компоноваться, не сливаться.
- НЕ domain/brand name-collision detection (совпадение имени бренда с чужим, как g4s.md vs международная G4S security) — остаётся кандидатом для `seo-audit-engine` (Vikunja #1855), не относится к этому плану.
- НЕ автоматический промоушен кандидата в tracked competitor — всегда человек.

**Рискованные действия запрещены:** приложение не должно формулировать конкурентов как факт без пометки источника — каждый кандидат обязан нести sourcing trail, иначе это недоказанное утверждение о реальном бизнесе третьей стороны.

## 7. Данные, конфиденциальность и интеграции

- **Минимально необходимые данные:** `brand_id`, `industry`, geography-контекст бренда (уже на `BrandProfile`); результат — текст (market summary, кандидаты, sourcing trail).
- **Источники данных:** `web-search` app (`web_search` + `read_url`) — но это системное приложение с `owner_chat_tool` (чат-уровня), НЕ IPC-вызываемое из backend через `ctx.extensions.call` (в отличие от `wordpress-hub`/`google-search-console-connector`, которые реально callable). Значит `run_market_research` не идёт в сеть сама — она принимает уже добытые сигналы как параметр (market summary + candidate list + sourcing trail), которые Webbee собирает через `web_search`/`read_url` заранее и передаёт в вызов. Это тот же паттерн, что `discover_opportunities` в Content Strategy Hub уже использует для `QuerySignal` (пре-фетчнутые GSC-сигналы, не самостоятельный fetch).
- **Что хранится vs остаётся ссылкой:** snapshot хранит summary-текст и список URL-источников (ссылки, не полные скачанные страницы) — тот же принцип, что VBS evidence (HTTPS-ссылка, не скачанный контент).
- **Retention/удаление:** снапшоты следуют тому же жизненному циклу, что SWOT/gap-анализ — `archive_gap_analysis`/`archive_swot_result`-подобный паттерн (пометка superseded, не физическое удаление) должен быть добавлен и для `MarketResearchSnapshot`.
- **Tenant isolation:** приватная VBS workspace-модель уже даёт tenant isolation на уровне бренда — snapshot наследует то же (виден только участникам workspace бренда).
- **Данные, которые нельзя отдавать третьим сторонам:** сам факт, что это внутренний рыночный анализ клиента — snapshot не должен покидать workspace бренда ни в каком построении handoff (в отличие от `build_content_strategy_handoff`, который специально предназначен для внешнего relay).
- **Статус интеграций:**
  - `web-search` (web_search, read_url) — **available**, уже используется в других приложениях платформы.
  - Собственный `industry`/geography на `BrandProfile` — **available**, уже есть поле `industry` (см. `schemas.py:28`), geography пока нет явного поля — **unverified**, требует discovery (см. открытые вопросы в `MARKET_RESEARCH_PLAN.md`: "как работает geography-grounding, если в профиле нет явной страны").

## 8. P0 — минимальный законченный полезный путь

**Главный use case:** Webbee сначала собирает рыночные сигналы через свой `web_search`/`read_url` (чат-уровня, не IPC), затем вызывает `run_market_research(brand_id, signals)` для бренда с заполненным `industry` → получает черновой `MarketResearchSnapshot` с кандидатами в конкуренты и market-контекстом, привязанным к переданным источникам → человек вручную промоутит релевантных через существующий `add_brand_competitor`.

**Обязательные сущности/действия:**
- Новая сущность `MarketResearchSnapshot` (см. предложенную форму в `MARKET_RESEARCH_PLAN.md`): `brand_id`, market-landscape summary, candidate competitor list, sourcing trail (queries/URLs), `is_current`/`superseded_at` — по образцу `SWOTResult`.
- Новый tool `run_market_research(brand_id, signals: list[MarketSignal])` — `signals` это уже собранные Webbee данные (найденные URL + краткий контент/summary), а не вызов из backend в web-search; тот же паттерн, что `discover_opportunities(site_id, queries: list[QuerySignal])` в Content Strategy Hub.
- Явная защита (server-side gate): отказ, если `industry` на профиле пуст ИЛИ `signals` пуст — не создавать снапшот без реального источника.

**Сознательно исключено из P0:** промоушен кандидата одним кликом/bulk-действием (открытый вопрос — решается после первой живой обратной связи); фид-через в `run_gap_analysis`/`run_swot_analysis` (второй срез, не первый).

**Acceptance criteria (простыми словами):** вызов `run_market_research` для бренда с заполненным industry возвращает снапшот с хотя бы одним источником в sourcing trail (не пустой список без объяснения) ИЛИ явный статус "insufficient market signal" — никогда не выдуманные конкуренты без trail.

## 9. UX-карта Imperal panel

- **Точка входа:** страница бренда в Brand Strategy Hub panel (там же, где уже видны SWOT/Gap Analysis карточки) — новая карточка "Market Research".
- **Первый экран:** если снапшотов ещё нет — empty state с кнопкой "Run market research" и коротким объяснением, что это делает web-поиск по industry бренда.
- **Primary next action:** после запуска — либо готовый снапшот с списком кандидатов и кнопкой "Add as tracked competitor" на каждого, либо явный blocked-state ("Заполните Industry в профиле бренда, чтобы запустить поиск").
- **States:**
  - *empty* — снапшотов ещё нет.
  - *in-progress* — запрос выполняется (web_search может занять время).
  - *blocked* — industry не заполнен, кнопка неактивна с пояснением.
  - *ready-for-review* — снапшот готов, кандидаты ждут решения человека.
  - *approved* — н/п в этом P0 (нет отдельного approval у самого снапшота, approval происходит на уровне конкретного competitor через существующий flow).
- **Ошибки/recovery:** если `web_search` не находит источников — снапшот всё равно сохраняется с пометкой "insufficient market signal", не выглядит как сбой системы.
- **Где виден результат:** карточка "Market Research" на странице бренда + промоутнутые конкуренты появляются в уже существующем списке `list_brand_competitors`.
- **App settings:** отдельных настроек для этой capability не предполагается (переиспользует существующие App settings Brand Strategy Hub) — если появится конфигурируемый параметр (например, глубина поиска), он войдёт в общий App settings по `UI_INTERFACE_STANDARD.md`.

## 10. Safety, approvals и audit trail

- **Что делает сама:** ищет и суммирует (web_search + read_url), пишет черновой снапшот.
- **Что только предлагает:** список кандидатов в конкуренты — никогда не пишет напрямую в `add_brand_competitor`.
- **Explicit confirmation:** каждый промоушен кандидата — это explicit-вызов `add_brand_competitor` человеком (уже существующий паттерн, не новый).
- **Named human approval:** не требуется для самого снапшота (это черновик для чтения, не финальное решение), но каждый факт "это наш конкурент" в `list_brand_competitors` уже подразумевает, что человек это выбрал.
- **Audit trail:** sourcing trail внутри снапшота — это и есть аудируемый след ("откуда взялось это утверждение"), обязателен для каждого снапшота, не опционален.
- **Fail closed:** если industry не заполнен или web-search недоступен — явный blocked-статус, не мнимый пустой "результат" без объяснения.

## 11. Discovery и проверка гипотезы

- **Кого интервьюируем:** vlad@bluebeeweb.com как первый реальный пользователь (владелец нескольких брендов в системе — Climtec, g4s.md, NordLuma, BlueBeeWeb) — реальный discovery, не гипотетический персонаж.
- **Вопросы:** насколько кандидаты в первом снапшоте (на реальных брендах типа g4s.md) совпадают с тем, что было найдено вручную в кейсе; достаточно ли sourcing trail, чтобы доверять снапшоту без перепроверки; нужен ли geography-контекст явным полем на профиле.
- **Артефакты:** сравнение "снапшот vs то, что я нашла вручную в кейсе g4s.md" — уже есть готовый эталон для первой проверки (ROMVENT, Amexpert, ClimatLux, vent.md).
- **Сколько наблюдений достаточно:** 2-3 бренда с реально заполненным industry (Climtec, g4s.md, NordLuma) достаточно для первого решения о качестве grounding — если кандидаты релевантны на всех трёх, P0 подтверждён.

## 12. План воплощения и live-критерии

**Репозиторий:** уже публичный (Brand Strategy Hub существующий репозиторий) — новый код входит туда же, без нового репо.

### Вертикальные срезы

| Срез | Проблема/flow | Panel location | Зависимости | Тесты | Критерий live verified | Статус |
|---|---|---|---|---|---|---|
| P0-A: схема + tool `run_market_research` | Снапшот создаётся и сохраняется с кандидатами и sourcing trail | Нет UI ещё — только вызов tool | `web-search` app (available) | Unit-тест на схему + happy/blocked path tool | Вызов через чат создаёт реальный снапшот на реальном бренде (g4s.md) | `planned` |
| P0-B: panel карточка "Market Research" на странице бренда | Видно в Imperal panel, не только в чате | Страница бренда, рядом с SWOT/Gap Analysis | P0-A | Panel render test (empty/blocked/ready states) | Стратег видит и запускает research прямо в panel, видит кандидатов | `planned` |
| P0-C: bulk-промоушен кандидатов | Не promоутить по одному, а выбрать несколько сразу | Та же карточка | P0-A, P0-B | Тест на bulk-call в `add_brand_competitor` | Стратег промоутит 2-3 кандидата за один клик в live panel | `planned` |

### Обязательный первый P0-срез
P0-A должен быть `live verified` (реально вызван на реальном бренде, снапшот сохранён и виден через `list_...`-эквивалент) прежде чем начинать P0-B.

### Later roadmap — не начинать до live verified P0

| Priority | Срез | Entry condition |
|---|---|---|
| P1 | Фид-через: `run_gap_analysis`/`run_swot_analysis` читают latest current `MarketResearchSnapshot`, если есть | P0 live verified минимум на 2 брендах, и хотя бы один SWOT/gap-анализ запущен ПОСЛЕ существования снапшота — проверить, реально ли меняется качество вывода |
| P1 | `archive_market_research_snapshot` (аналог `archive_swot_result`) | Появился хотя бы один случай, когда старый снапшот реально мешает (устарел, вводит в заблуждение) |
| P2 | Явное geography-поле на `BrandProfile`, если grounding без него окажется слабым | Discovery (раздел 11) показывает, что кандидаты нерелевантны из-за отсутствия explicit geography на 2+ брендах |
| P2 | Bulk/scheduled research (переход от callable к периодическому) | Явный запрос пользователя переоценить рынок регулярно, а не по требованию — сейчас сознательно НЕ входит (раздел 6) |
| P3 | Domain/brand name-collision check (перекрёстная ссылка на `seo-audit-engine`, Vikunja #1855) | Отдельная задача, не блокирует этот план; переоценить, только если #1855 реализуется и нужен общий источник данных |

## 13. Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-08-17 | Market Research — capability внутри Brand Strategy Hub, не отдельное приложение | Питает уже существующие `run_gap_analysis`/`run_swot_analysis`; отдельное приложение добавило бы IPC-overhead без выгоды |
| 2026-08-17 | Tender monitoring — не строим, ни здесь, ни отдельно | Узкий частный случай B2B lead sourcing, не оправдывает постоянную инженерную поддержку (см. `MARKET_RESEARCH_PLAN.md`) |
| 2026-08-17 | Sales-side prospecting/outreach/CRM — выносится в отдельный концепт Sales Strategy Hub | Разная семантика жизненного цикла (prospect→contacted→won/lost — это не бренд и не SWOT), разная будущая интеграционная поверхность (CRM) |
| 2026-08-17 | Domain/brand name-collision detection — остаётся кандидатом для seo-audit-engine, не для этого плана | Технический SEO/аудит-слой, не про рыночный контекст бренда |
| 2026-08-17 | Промоушен кандидата в tracked competitor — всегда вручную, никогда автоматически | Human-in-the-loop принцип, тот же, что у VBS evidence review — снапшот не должен молча становиться "фактом" о реальном третьем бизнесе |

## 14. Live verification log

| Date | What was verified | Result |
|---|---|---|
| 2026-08-17 | Код смёржен (commit `c7655a8`, запушен в `main`), `imperal_sdk validate` → 0 errors/0 warnings, `pytest` → 62/62 passed, `deploy_app` → задеплоено на коммит `c7655a87` (46 tools синхронизировано). | OK |
| 2026-08-17 | Live-вызов `run_market_research` через реальный задеплоенный IPC (не MockContext) для бренда `g4s.md` (industry: инженерные системы HVAC) с 6 реальными signals, собранными самой Webbee через `web_search` (romvent.md, ditrade.md, climatlux.md, laiola.md, ecoventexpert.md, conditionere.md). | Снапшот создан, `is_current=true`, 6 candidate_competitors, полный sourcing trail из 6 реальных URL — никаких выдуманных конкурентов. |
| 2026-08-17 | `list_market_research_results(brand_id=g4s.md)` живьём после создания. | Возвращает ровно тот снапшот, `is_current=true`, тело в Markdown корректно рендерится. |

P0 для Market Research (создание снапшота, gate на пустой industry/signals, list, archive, cascade delete/purge, панель) — **live verified**. Не проверено вживую в этом проходе: `archive_market_research_result` (логика идентична уже проверенному `archive_swot_result`, локально протестирована) и панельная вкладка Market Research в самом Imperal panel UI (проверена только по коду/паттерну, не кликом в браузере).
