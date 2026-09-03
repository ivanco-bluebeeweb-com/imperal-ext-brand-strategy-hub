# Brand Strategy Hub — UI component plan

Источники: `Docs/session-notes/UI_COMPONENT_VOCABULARY.md`, `UI_INTERFACE_STANDARD.md`,
`concepts/panels.md`. Основано на функционале `brand-strategy-hub` (профили бренда,
target segments, SWOT/gap-анализ, Visual Brand System — без внешнего `connect_*`).

## 0. Разница с реализацией сейчас
Нет формы подключения аккаунта — первое реальное действие это создание профиля
бренда. Стоит выровнять по стандарту:
- Первый экран — прямая форма `create_brand_profile`, не generic `Empty` с
  инструкцией "подключитесь", которой здесь нет.
- Форма растянута на всю ширину контейнера, поля с лейблами и контекстными
  плейсхолдерами-примерами (не голые "введите миссию").
- Visual Brand System (draft→activate) — отдельный явный поток от текстового
  профиля, не смешивать в одном экране.

## 1. Компоненты

| Экран | Примитивы | Почему именно эти |
|---|---|---|
| Sidebar (left) | `ui.Column`(align="start") + `ui.Divider` + navigation `ui.ListItem`(Brands/Segments/Competitors/Visual Brand System) + `ui.Button`("App settings") | Без карточек, по стандарту. |
| Empty (нет брендов) | `ui.EmptyState`(title="Создайте профиль бренда", body, `ui.Button`("+ Создать профиль") → Brand Profile Form) | Прямой CTA, без надуманного шага подключения. |
| Brand Profile Form | `ui.Form`(action="create_brand_profile") + `ui.Input`(label="Название бренда", placeholder="напр. Acme Coffee") + `ui.TextArea`(label="Миссия", placeholder="Пример: Сделать качественный кофе доступным каждому") + `ui.TextArea`(label="Ценностное предложение", placeholder="Пример: единственный на рынке, кто...") + `ui.Select`(label="Тон голоса", options=[дружелюбный, экспертный, дерзкий...]) | Все поля с лейблами, плейсхолдеры-примеры, а не пустые подсказки. |
| Brand List | `ui.DataTable`(name, segments count, last updated; sortable) | Обзор брендов для агентства с несколькими клиентами. |
| Target Segment Form | `ui.Form`(action="create_target_segment") + `ui.Input`(label="Название сегмента", placeholder="напр. Молодые профессионалы 25-35") + `ui.TextArea`(demographics/psychographics/pain points, каждое с лейблом) | Прямое продолжение после создания профиля. |
| Competitor List | `ui.DataTable`(name, strengths, weaknesses; sortable) + `ui.Button`("+ Добавить конкурента") | Трекинг конкурентов бренда. |
| Gap/SWOT Result | `ui.KeyValue`(summary) + `ui.DataTable`(findings; sortable) + `ui.Badge`(archived/current) | Снимки анализа с историей версий. |
| Visual Brand System | `ui.Timeline`(draft→review→activated ревизии) + `ui.Button`("Создать новую ревизию") | Явно отдельный поток версий, не смешан с текстовым профилем. |
| App Settings | `ui.Accordion`([Membership management, Purge data]) | Централизованные настройки по стандарту. |

## 2. User flow (валидно по panel lifecycle)

1. **SESSION INIT, нет брендов** → Empty с CTA "+ Создать профиль" → Brand Profile
   Form → `create_brand_profile` → редирект на созданный профиль.
2. После создания профиля → ненавязчивый `ui.Alert`(info) "Определите целевую
   аудиторию" с CTA → Target Segment Form.
3. Brand List → клик на бренд → детальный экран бренда (профиль + сегменты +
   конкуренты + последние SWOT/gap снимки, вкладками или Accordion).
4. Detail → "Запустить SWOT-анализ"/"Запустить gap-анализ" → `run_swot_analysis`/
   `run_gap_analysis` → результат сразу в Gap/SWOT Result.
5. Visual Brand System — отдельный пункт в sidebar, доступен независимо от текстового
   профиля; "Создать новую ревизию" → `create_visual_brand_system` → Timeline
   обновляется.
6. App Settings — доступен из sidebar в любой момент.

## 3. Экраны/карточки (конкретно для этого приложения)

- **Screen: Empty + CTA** — EmptyState + Button.
- **Screen: Brand Profile Form** — Form(4 поля, растянута на ширину контейнера).
- **Screen: Brand List** — DataTable(3 колонки).
- **Screen: Target Segment Form** — Form(4 поля).
- **Screen: Competitor List** — DataTable(3 колонки) + Button.
- **Screen: Gap/SWOT Result** — KeyValue + DataTable + Badge.
- **Screen: Visual Brand System** — Timeline + Button.
- **Screen: App Settings** — Accordion(2 секции).

Ограничение SDK, учтённое в плане: multi-tenant membership (VBS workspace) добавляет
роли (owner/reviewer) — отражено через `ui.Badge`(role) на Timeline-записях, отдельного
role-management примитива в инвентаре нет, используется Accordion в App Settings.
