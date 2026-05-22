"""
Шаблоны постов для публикации вакансий в Telegram-канал.

Используется HTML parse_mode для корректного отображения
форматирования в Telegram (без проблем экранирования MarkdownV2).
"""

import re
import html as html_lib


def format_salary(vacancy: dict) -> str:
    """Форматирует зарплату в читаемый вид с разделителями тысяч.

    Поддерживает варианты: «от X», «до X», «X – Y», «не указана».

    Args:
        vacancy: словарь вакансии с полями salary_from / salary_to.

    Returns:
        Строка с отформатированной зарплатой и символом ₽.
    """
    salary_from = vacancy.get("salary_from")
    salary_to = vacancy.get("salary_to")

    try:
        if salary_from and salary_to:
            return f"{salary_from:,} – {salary_to:,} ₽".replace(",", " ")
        if salary_from:
            return f"от {salary_from:,} ₽".replace(",", " ")
        if salary_to:
            return f"до {salary_to:,} ₽".replace(",", " ")
    except (TypeError, ValueError):
        pass

    return "не указана"


def slugify(text: str) -> str:
    """Превращает текст в хештег-совместимый формат.

    Оставляет только кириллические и латинские буквы, цифры.
    Переводит в нижний регистр, убирает пробелы.

    Args:
        text: исходный текст (название вакансии, компании и т.д.).

    Returns:
        Строка, пригодная для использования как Telegram-хештег.
    """
    # Оставляем кириллицу, латиницу и цифры
    cleaned = re.sub(r"[^а-яёa-z0-9]", "", text.lower())
    # Ограничиваем длину, чтобы хештег не был слишком длинным
    return cleaned[:30] if cleaned else "вакансия"


def _escape_html(text: str) -> str:
    """Экранирует спецсимволы HTML для безопасной вставки в шаблон.

    Args:
        text: сырой текст.

    Returns:
        Экранированный текст (& → &amp;, < → &lt;, > → &gt;).
    """
    if not text:
        return ""
    return html_lib.escape(str(text))


def format_post(vacancy: dict) -> str:
    """Форматирует полный пост для публикации вакансии в канал.

    Использует HTML parse_mode — жирный текст через <b>,
    ссылки через <a href>.

    Args:
        vacancy: нормализованный словарь с полями:
            title, company, salary_from, salary_to, schedule,
            description, requirements, url, area, source.

    Returns:
        Готовый HTML-текст поста.
    """
    try:
        title = _escape_html(vacancy.get("title", "Без названия"))
        company = _escape_html(vacancy.get("company", "не указана"))
        salary = _escape_html(format_salary(vacancy))
        schedule = _escape_html(vacancy.get("schedule", "Удалённая работа"))
        area = _escape_html(vacancy.get("area", "Вся Россия"))
        url = vacancy.get("url", "")

        # Описание и требования — обрезаем и экранируем
        description_raw = vacancy.get("description", "Подробнее по ссылке") or "Подробнее по ссылке"
        requirements_raw = vacancy.get("requirements", "Подробнее по ссылке") or "Подробнее по ссылке"
        description = _escape_html(description_raw[:300])
        requirements = _escape_html(requirements_raw[:200])

        # Хештег из источника
        source = vacancy.get("source", "")
        source_tag = slugify(source) if source else "работа"

        post = (
            f"💼 <b>{title}</b>\n"
            f"\n"
            f"🏢 Компания: {company}\n"
            f"💰 Зарплата: {salary}\n"
            f"📍 Формат: {schedule}\n"
            f"🗺️ Регион: {area}\n"
            f"\n"
            f"📝 <b>О задачах:</b>\n"
            f"{description}...\n"
            f"\n"
            f"✅ <b>Требования:</b>\n"
            f"{requirements}...\n"
            f"\n"
            f'🔗 <a href="{url}">Смотреть вакансию</a>\n'
            f"\n"
            f"#удалёнка #вакансия #{source_tag}"
        )

        return post

    except Exception:
        # Минимальный fallback — просто ссылка
        return (
            f"💼 <b>{_escape_html(vacancy.get('title', 'Вакансия'))}</b>\n"
            f'🔗 <a href="{vacancy.get("url", "")}">Открыть вакансию</a>'
        )


def format_post_short(vacancy: dict) -> str:
    """Форматирует короткий пост для вакансий без описания.

    Args:
        vacancy: нормализованный словарь с полями:
            title, company, salary_from, salary_to, url.

    Returns:
        Готовый HTML-текст короткого поста.
    """
    try:
        title = _escape_html(vacancy.get("title", "Без названия"))
        company = _escape_html(vacancy.get("company", "—"))
        salary = _escape_html(format_salary(vacancy))
        url = vacancy.get("url", "")

        post = (
            f"💼 <b>{title}</b>\n"
            f"🏢 {company} | 💰 {salary} | 🌐 Удалённо\n"
            f"\n"
            f'🔗 <a href="{url}">Открыть вакансию</a>\n'
            f"\n"
            f"#удалёнка #вакансия"
        )

        return post

    except Exception:
        return (
            f"💼 <b>{_escape_html(vacancy.get('title', 'Вакансия'))}</b>\n"
            f'🔗 <a href="{vacancy.get("url", "")}">Открыть вакансию</a>'
        )
