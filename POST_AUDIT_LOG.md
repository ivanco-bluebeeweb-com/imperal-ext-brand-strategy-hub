# Post-Audit Log — Brand Strategy Hub

Формат и правила ведения: см. `/Users/vladivanco/Documents/Imperal OS/POST_AUDIT_LOG_STANDARD.md`.
Новые записи добавляются СВЕРХУ.

---

## 2026-08-19 — Plausible Scenario Testing (PST) — чистый прогон, единственный пробел закрыт

Полный метод и детали — в `SCENARIO_TESTS.md` этого приложения. Кратко:
существующие 113 тестов уже покрывали happy/error/adversarial ветки
достаточно широко; аудит нашёл один реальный пробел — отсутствие
recovery-сценариев — закрыт 7 новыми тестами в `tests/test_pst_scenarios.py`.
Полный набор (119 тестов) зелёный. Реальных багов в коде приложения не
найдено; три собственные ошибочные гипотезы в черновике PST-сценариев
исправлены (подробности в SCENARIO_TESTS.md) — во всех трёх случаях
выяснилось, что код уже защищает инварианты строже, чем предполагал
первоначальный сценарий.

---

## 2026-08-19 — Сквозной пост-аудит + исправление double-prompt антипаттерна

**Что проверялось:** py_compile всех модулей; количество `@chat.function`
(46, совпадает с манифестом); все `delete`/`archive`/`revoke`/`purge`
функции и их `action_type`; наличие ручного поля `confirm*` рядом с уже
корректным `action_type="destructive"` (доктрина Imperal: confirmation
card рендерится ТОЛЬКО по `action_type`, повторная проверка внутри
хендлера — double-prompt антипаттерн, ломающий гарантию платформы "что
видел — то и выполнится"); полный прогон тестового набора (`tests/`, 113
тестов через `.venv`).

**Метод:** grep по `schemas.py`/`main.py` на `confirm` в любом виде;
сверка каждой найденной функции с её `action_type` в манифесте; для
функций, УЖЕ `destructive`, любое дополнительное поле `confirm*` —
подтверждённый баг (в отличие от функций, где confirm* — единственный
существующий гейт на `action_type="write"`, где платформенная карточка
вообще не показывается — это не тот же баг и не трогалось); правки
применены к `schemas.py`, `main.py`, синхронизированы в `imperal.json`
(params_schema очищен от убранных полей); `python3 -m py_compile`; полный
`pytest` прогон до и после.

### Находки

1. **`delete_brand_profile`** — `action_type="destructive"` (корректно
   гейтит через платформенную карточку), но хендлер ДОПОЛНИТЕЛЬНО требовал
   ручное `confirm_cascade=true` и возвращал ошибку без него. Double-prompt
   баг: пользователь видел бы платформенную карточку с полным описанием
   каскада, нажимал "Да", и затем получал вторую ошибку с требованием
   передать ещё один флаг вручную.
2. **`purge_brand_strategy_data`** — тот же баг с полем `confirm_wipe`.
3. **`initialize_visual_brand_workspace`** — проверено: имеет
   `confirm_owner_claim`, но `action_type="write"` (платформенная карточка
   НЕ рендерится для write). Здесь ручной флаг — единственный существующий
   гейт для намеренного бизнес-решения ("заявить владение чужим legacy-
   брендом"), а не дублирование платформенного гейта. НЕ являлось багом,
   не тронуто.
4. Найдены 2 теста в `tests/test_smoke.py`, которые проверяли именно
   убранное (ошибочное) поведение — `test_delete_brand_profile_requires_confirm_cascade`
   и `test_purge_brand_strategy_data_requires_confirm_wipe` — оба ожидали
   `status == "error"` без ручного confirm-флага. Устарели вместе с
   исправлением бага, не являются регрессией.

### Что сделано

1. `schemas.py`: убрано поле `confirm_cascade` из `DeleteBrandProfileParams`
   и `confirm_wipe` из `PurgeBrandStrategyDataParams` (с explaining
   docstring на будущее, почему пусто).
2. `main.py`: убраны обе ручные проверки `if not params.confirm_cascade`
   / `if not params.confirm_wipe` и упоминания требуемых флагов из текстов
   описаний инструментов.
3. `imperal.json`: синхронизирован — оба поля убраны из `params_schema`
   обеих функций (properties + required).
4. `tests/test_smoke.py`: два устаревших теста переписаны под новое
   корректное поведение (`test_delete_brand_profile_without_confirm_still_deletes`,
   `test_purge_brand_strategy_data_without_confirm_still_runs` — оба теперь
   ожидают `status == "success"` без ручного confirm); третий тест
   (`test_delete_brand_profile_cascades_to_every_dependent`) убрал
   устаревший kwarg `confirm_cascade=True` из вызова.
5. Проверено: `python3 -m py_compile *.py` — чисто; полный прогон
   `pytest tests/` — 113/113 passed после правок.
6. Приложение НЕ имеет `pricing` в `imperal.json` — ценообразование не
   входит в этот аудит (по PRICING_POLICY.md ценообразование — последний
   шаг, только после чистого пост-аудита; будет отдельным шагом позже).

**Статус: FIXED.** Оба найденных double-prompt-бага устранены и
подтверждены тестами; вопрос по `initialize_visual_brand_workspace`
рассмотрен и закрыт как не являющийся тем же классом проблемы.
