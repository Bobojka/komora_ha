# Комора для Home Assistant

Інтеграція домашнього обліку запасів [Комора](https://github.com/Bobojka/komora) рідними засобами Home Assistant.

## Що дає

- **Список «Покупки»** (`todo.komora_shopping_list`) — той самий, що в Коморі: прогноз + додане вручну.
  - Додати: «молоко» або «молоко 2» (назву можна з помилкою).
  - Поставити галочку — «куплено»: надходження у звичне місце, кількість — скільки радив список.
  - Видалити — не пропонувати до кінця горизонту.
- **Сенсори:** «Покупки», «Закінчується», «Треба доїсти» — кількість позицій, перелік в атрибутах `items` і `names`.
- **Дії:** `komora.write_off`, `komora.receive`, `komora.add_to_shopping` — позиція назвою або id; причина, місце й кількість за звичкою. Повертають відповідь (id документа).
- **Пошук:** `komora.find` (лише з відповіддю) — «скільки є»: до `limit` позицій за назвою (можна з помилкою), для кожної `name`, `amount` («20 pcs», «рівень 2», «мало»), `qty`, `unit`, `locations`. Нею користується голосовий асистент ([voice_assistant_ha](https://github.com/Bobojka/voice-assistant-ha)).
- **Панель «Комора»** у бічному меню — увесь інтерфейс Комори всередині HA.
- Живі оновлення: зміни в Коморі (з телефона, Claude, вебу) приходять за секунду через потік подій.

## Встановлення

1. HACS → ⋮ → Custom repositories → `https://github.com/Bobojka/komora_ha`, тип Integration → «Комора» → Download.
2. Перезапустити Home Assistant.
3. Комора → Адміністрування → Токени → новий токен, джерело «Home Assistant (голос)».
4. Налаштування → Пристрої та служби → Додати інтеграцію → «Комора»: адреса і токен.

Для панелі на сервері Комори в `.env`:

```
KOMORA_FRAME_ANCESTORS=https://hass.example.com
```

Вхід у панелі — звичайний вхід Комори (один раз; cookie працює, якщо HA і Комора на одному домені, напр. `hass.example.com` і `komora.example.com`).

## Параметри

Налаштування інтеграції → «Налаштувати»: панель у меню (так/ні), горизонт покупок (днів), поріг «треба доїсти» (днів).

## Приклад

```yaml
action: komora.write_off
data:
  item: вода
  qty: 1
```

---

**English.** Home Assistant integration for the Komora home inventory: a native to-do shopping list
(complete = bought, received into the usual place), sensors (shopping, running out, eat first),
actions (`write_off`, `receive`, `add_to_shopping`), a sidebar panel (iframe; set
`KOMORA_FRAME_ANCESTORS` on the Komora server) and live updates over server-sent events.
Install via HACS (custom repository) or copy to `custom_components/komora`, then add the
integration with the Komora URL and an API token.
