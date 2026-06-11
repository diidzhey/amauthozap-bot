from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import re
import json
import csv
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import time
from dotenv import load_dotenv
load_dotenv()  # загружает переменные из файла .env

# подключаем фреймворк
app = Flask(__name__)
app.jinja_env.auto_reload = True
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Настройки OpenRouter API
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "google/gemini-2.0-flash-exp:free"

if not OPENROUTER_API_KEY:
    raise ValueError("❌ Вставьте API-ключ OpenRouter!")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "Amautozap Bot",
    }
)


#Записывает в CSV диалог и время ответа
def log_dialog(session_id, user_message, bot_reply, response_time_ms):
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    filepath = os.path.join(log_dir, "dialogs.csv")
    
    file_exists = os.path.isfile(filepath)
    
    with open(filepath, "a", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "session_id", "user_message", "bot_reply", "response_time_ms"])
        writer.writerow([
            datetime.now().isoformat(),
            session_id,
            user_message.replace("\n", " ").replace(",", ";"),
            bot_reply.replace("\n", " ").replace(",", ";"),
            response_time_ms
        ])

# Настройки email-уведомлений
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def send_email_notification(phone: str, dialog_summary: str, reason: str = "Эскалация от чат-бота") -> bool:
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER
        msg["Subject"] = f"Amautozap - {reason}"

        html_body = f"""
        <html><head><style>
            body {{ font-family: Arial, sans-serif; }}
            .header {{ background-color: #1a3c6c; color: white; padding: 15px; }}
            .content {{ padding: 20px; }}
            .phone {{ font-size: 24px; font-weight: bold; color: #ff6b35; }}
            .dialog {{ background-color: #f5f5f5; padding: 15px; border-radius: 8px; font-family: monospace; }}
            .time {{ color: #666; font-size: 12px; }}
        </style></head><body>
            <div class="header"><h2>Amautozap - Требуется внимание оператора!</h2></div>
            <div class="content">
                <h3>📞 Контактный номер:</h3><p class="phone">{phone}</p>
                <h3>📝 Краткое резюме диалога:</h3>
                <div class="dialog">{dialog_summary.replace(chr(10), '<br>')}</div>
                <p class="time">Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</p>
            </div>
        </body></html>
        """
        msg.attach(MIMEText(html_body, "html"))

        server = smtplib.SMTP(SMTP_SERVER, 465)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Ошибка отправки email: {e}")
        return False


# Пути к базам знаний
KB_FOLDER = os.path.join(os.path.dirname(__file__), "kb")


def load_knowledge_base(filepath: str) -> list:
    knowledge = []
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:   # ← ключевое изменение
            reader = csv.DictReader(f)   # разделитель по умолчанию ','
            for row in reader:
                # Теперь ключи будут корректными: 'mark', 'model', ...
                knowledge.append({
                    "mark": row["mark"].strip(),
                    "model": row["model"].strip(),
                    "year_start": int(row["year_start"]) if row["year_start"].strip() else None,
                    "year_end": int(row["year_end"]) if row["year_end"].strip() else None,
                    "engine": float(row["engine"]) if row["engine"].strip() else None,
                    "symptom": row["symptom"].strip(),
                    "cause": row["cause"].strip(),
                    "parts": [p.strip() for p in row["parts"].split(",") if p.strip()],
                    "examples": row["examples"].strip()
                })
    except Exception as e:
        print(f"Ошибка загрузки knowledge_base.csv: {e}")
        import traceback
        traceback.print_exc()
    return knowledge


def load_analogs_db(filepath: str) -> dict:
    """Загружает базу аналогов из CSV-файла с разделителем ';'."""
    analogs = {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                original = row["PART_NUMBER"].strip()
                analogs_list = []
                # Аналог 1
                if row.get("ANALOG1"):
                    analog1 = row["ANALOG1"].strip()
                    price1 = row.get("PRICE1", "").strip()
                    if price1:
                        analogs_list.append(f"{analog1} ({price1} руб.)")
                    else:
                        analogs_list.append(analog1)
                # Аналог 2
                if row.get("ANALOG2"):
                    analog2 = row["ANALOG2"].strip()
                    price2 = row.get("PRICE2", "").strip()
                    if price2:
                        analogs_list.append(f"{analog2} ({price2} руб.)")
                    else:
                        analogs_list.append(analog2)
                if analogs_list:
                    analogs[original] = analogs_list
    except Exception as e:
        print(f"Ошибка загрузки analogs_db.csv: {e}")
    return analogs


def load_catalog(filepath: str) -> list:
    catalog = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    row["year_start"] = int(row["year_start"])
                    row["year_end"] = int(row["year_end"])
                    row["engine"] = float(row["engine"])
                    row["price"] = int(row["price"])
                    catalog.append(row)
                except (ValueError, KeyError):
                    continue
    except Exception as e:
        print(f"Ошибка загрузки catalog.csv: {e}")
    return catalog


# Загрузка баз данных при старте приложения
KNOWLEDGE_BASE = load_knowledge_base(os.path.join(KB_FOLDER, "knowledge_base.csv"))
ANALOGS_DB = load_analogs_db(os.path.join(KB_FOLDER, "analogs_db.csv"))
CATALOG = load_catalog(os.path.join(KB_FOLDER, "catalog.csv"))

# Вывод количества загруженных записей (как в первом коде)
print(f"✅ Каталог запчастей: {len(CATALOG)} записей")
print(f"✅ База знаний: {len(KNOWLEDGE_BASE)} записей")
print(f"✅ База аналогов: {len(ANALOGS_DB)} записей")


# Функции для работы с артикулами
def normalize_part(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9\s]", "", s)).strip().upper()


def extract_part_number(text: str) -> str:
    candidates = re.findall(r'[A-Z0-9][A-Z0-9\s\.\-_]{4,}', text.upper())
    for cand in candidates:
        clean = normalize_part(cand)
        if len(clean) >= 5 and any(c.isdigit() for c in clean):
            return clean
    return normalize_part(text)


def find_analogs(part_number: str) -> str:
    query_norm = normalize_part(part_number)
    for key in ANALOGS_DB:
        key_norm = normalize_part(key)
        if query_norm == key_norm:
            return ", ".join(ANALOGS_DB[key])
    return ""


def extract_car_info_with_llm(chat_history: list) -> dict:
    user_messages = [u for u, b in chat_history if u and isinstance(u, str)]
    text = " ".join(user_messages)
    prompt = f"""
Ты — ассистент по подбору автозапчастей. Извлеки из текста параметры автомобиля.

Правила:
- Марка: определи марку на АНГЛИЙСКОМ языке.
  Соответствия русских названий английским:
  "Киа", "Kia", "КИА" → "Kia"
  "Тойота", "Toyota", "ТОЙОТА", "тоиота" → "Toyota"
  "Хёндэ", "Hyundai", "Хендай" → "Hyundai"
  "Фольксваген", "Volkswagen", "ФВ" → "Volkswagen"
  "БМВ", "BMW" → "BMW"
  "Мерседес", "Mercedes" → "Mercedes"
  "Ауди", "Audi" → "Audi"
  "Ниссан", "Nissan" → "Nissan"
  "Хонда", "Honda" → "Honda"
  "Форд", "Ford" → "Ford"
  "Рено", "Renault" → "Renault"
  "Шкода", "Skoda" → "Skoda"

- Модель: определи модель на АНГЛИЙСКОМ языке.
  Соответствия русских названий английским:
  "Рио", "Rio" → "Rio"
  "Камри", "Camry" → "Camry"
  "Солярис", "Solaris" → "Solaris"
  "Фокус", "Focus" → "Focus"
  "XC90" → "XC90"
  "w211" → "W211"
  "X5" → "X5"

- Год: только 4 цифры (2012, 2020) — если написано "12-го года", верни "2012"
- Объём: число с точкой, в литрах (1.4, 2.0, 1.6)

ВАЖНО: Если пользователь указал год, но не указал объём — год извлекай, объём оставь пустым.
Если пользователь указал объём, но не указал год — объём извлекай, год оставь пустым.

Ответь ТОЛЬКО валидным JSON без пояснений.

Примеры:
Текст: "Киа Рио 2012 года, движок 1.4"
Ответ: {{"brand": "Kia", "model": "Rio", "year": "2012", "engine": "1.4"}}

Текст: "Тойота Камри 2015 2.5"
Ответ: {{"brand": "Toyota", "model": "Camry", "year": "2015", "engine": "2.5"}}

Текст: "нужны свечи зажигания на тойота камри"
Ответ: {{"brand": "Toyota", "model": "Camry", "year": "", "engine": ""}}

Текст: "камри 2.5"
Ответ: {{"brand": "", "model": "Camry", "year": "", "engine": "2.5"}}

Текст: "тойота 2015"
Ответ: {{"brand": "Toyota", "model": "", "year": "2015", "engine": ""}}

Текст: "{text}"
"""
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=200
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("\n", 1)[0]
        data = json.loads(raw)
        year = str(data.get("year", "")).strip()
        if year.isdigit() and int(year) > 2026:
            year = ""
        return {
            "brand": str(data.get("brand", "")).strip(),
            "model": str(data.get("model", "")).strip(),
            "year": year,
            "engine": str(data.get("engine", "")).strip()
        }
    except Exception as e:
        print(f"Ошибка extract_car_info_with_llm: {e}")
        return {"brand": "", "model": "", "year": "", "engine": ""}


def extract_part_name_from_query(user_query: str, chat_history: list) -> str:
    prompt = f"""
Ты — ассистент по подбору автозапчастей. Извлеки название запчасти из запроса.

Правила:
- Верни только название запчасти в именительном падеже, без лишних слов.
- Если запрос общий ("фильтр", "тормоза") — верни как есть.
- Если запрос конкретный ("масляный фильтр", "тормозные колодки") — верни как есть.
- Если запчасть не указана — верни пустую строку.
- ОТВЕТЬ ТОЛЬКО названием запчасти, без кавычек, без пояснений.

Примеры:
"мне нужны тормозные колодки на киа рио" → тормозные колодки
"хочу купить масляный фильтр" → масляный фильтр
"свечи зажигания" → свечи зажигания
"нужен фильтр" → фильтр
"киа рио 2012" → 
"колодки" → тормозные колодки

Запрос: "{user_query}"
"""
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=30
        )
        part_name = resp.choices[0].message.content.strip().lower()
        # Убираем лишние символы и служебные слова 
        for bad in ['"', "'", "запрос:", "ответ:", "запчасть:", "пользователь:"]:
            part_name = part_name.replace(bad, "").strip()
        if len(part_name) > 40 or part_name in ["", "нет", "неизвестно", "ошибка"]:
            query_lower = user_query.lower()
            # Ключевые слова
            for part in ["тормозные колодки", "масляный фильтр", "воздушный фильтр", 
                         "топливный фильтр", "салонный фильтр", "свечи зажигания",
                         "тормозные диски", "моторное масло", "колодки", "фильтр", "свечи"]:
                if part in query_lower:
                    return part
            return ""
        return part_name
    except Exception as e:
        print(f"Ошибка extract_part_name_from_query: {e}")
        query_lower = user_query.lower()
        for part in ["тормозные колодки", "масляный фильтр", "воздушный фильтр", 
                     "топливный фильтр", "салонный фильтр", "свечи зажигания",
                     "тормозные диски", "моторное масло", "колодки", "фильтр", "свечи"]:
            if part in query_lower:
                return part
        return ""


def clarify_part_type_with_llm(query: str, chat_history: list) -> str:
    for u, b in chat_history[-5:]:
        if b and "🔍 Уточните, пожалуйста" in b:
            return None

    all_text = " ".join([u for u, b in chat_history if u] + [query]).lower()

    # Расширенный список конкретных запчастей
    specific_parts = [
        "масляный фильтр", "воздушный фильтр", "топливный фильтр", "салонный фильтр",
        "тормозные колодки", "тормозные диски", "тормозная жидкость", "тормозной цилиндр",
        "свечи зажигания", "свечи накала",
        "моторное масло", "трансмиссионное масло",
        "ремень грм", "ремень генератора", "ремень навесного оборудования",
        "помпа", "термостат", "радиатор",
        "амортизатор", "пружина", "подвеска",
        "колодки", "диски"
    ]
    for part in specific_parts:
        if part in all_text:
            return None

    # Категории для уточнения
    general_categories = {
        "фильтр": ["фильтр"],
        "тормоз": ["тормоз", "тормоза"],
        "масло": ["масло"],
        "свеч": ["свеча", "свечи"],
        "ремень": ["ремень", "ремни"],
    }

    found_categories = []
    for category, keywords in general_categories.items():
        for keyword in keywords:
            if keyword in all_text:
                found_categories.append(category)
                break

    if len(found_categories) != 1:
        return None

    category = found_categories[0]

    clarifications = {
        "фильтр": (
            "🔍 Уточните, пожалуйста, какой фильтр вам нужен:\n"
            "• Масляный\n"
            "• Воздушный\n"
            "• Топливный\n"
            "• Салонный"
        ),
        "тормоз": (
            "🔍 Уточните, пожалуйста, что именно вам нужно для тормозной системы:\n"
            "• Тормозные колодки\n"
            "• Тормозные диски\n"
            "• Тормозная жидкость\n"
            "• Тормозной цилиндр"
        ),
        "масло": (
            "🔍 Уточните, пожалуйста, какое масло вам нужно:\n"
            "• Моторное масло\n"
            "• Трансмиссионное масло\n"
            "• Гидравлическое масло"
        ),
        "свеч": (
            "🔍 Уточните, пожалуйста, какие свечи вам нужны:\n"
            "• Свечи зажигания\n"
            "• Свечи накала"
        ),
        "ремень": (
            "🔍 Уточните, пожалуйста, какой ремень вам нужен:\n"
            "• Ремень ГРМ\n"
            "• Ремень генератора\n"
            "• Ремень навесного оборудования"
        ),
    }
    return clarifications.get(category, None)


def filter_matches_with_llm(part_name_from_llm: str, matched_items: list, car_info: dict) -> list:
    if not matched_items:
        return []
    items_text = ""
    for i, item in enumerate(matched_items):
        items_text += f"{i+1}. {item}\n"
    car_info_str = f"{car_info['brand']} {car_info['model']} {car_info['year']} г., {car_info['engine']} л"

    prompt = f"""
Ты — ассистент по подбору автозапчастей.
Пользователь ищет: "{part_name_from_llm}"
Для автомобиля: {car_info_str}

Вот список запчастей из каталога, которые технически подходят по параметрам авто:

{items_text}

Твоя задача: выбрать ТОЛЬКО те запчасти, которые ДЕЙСТВИТЕЛЬНО соответствуют запросу пользователя по смыслу.

Правила:
- Если пользователь ищет "масляный фильтр", а в списке есть "масляный фильтр" — оставь его.
- Если пользователь ищет "тормозные колодки", а в списке есть "колодки тормозные" (или похожее) — оставь.
- Если пользователь ищет "воздушный фильтр", а в списке только "масляный фильтр" — не оставляй ничего.
- Если пользователь ищет "свечи зажигания", а в списке есть "свечи зажигания" — оставь.
- Если пользователь ищет общую категорию (например, "фильтр") — оставь все похожие (масляный, воздушный и т.д.).

Верни ТОЛЬКО номера пунктов (через запятую) из списка выше, которые подходят.
Если ничего не подходит, верни "НЕТ".

Пример ответа: "1,3,5"
"""
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=100
        )
        result = resp.choices[0].message.content.strip()
        if result == "НЕТ" or not result:
            return []
        numbers = re.findall(r'\d+', result)
        indices = [int(n) - 1 for n in numbers if 1 <= int(n) <= len(matched_items)]
        return [matched_items[i] for i in indices]
    except Exception as e:
        print(f"Ошибка LLM-фильтрации: {e}")
        return matched_items


def check_reset_with_llm(query: str, chat_history: list) -> tuple:
    """Проверка, хочет ли пользователь начать новый поиск для другого автомобиля"""
    
    # проверяем, не было ли уже сброса в этом диалоге
    if chat_history and len(chat_history) > 0:
        last_bot_reply = chat_history[-1][1]
        if last_bot_reply and "Давайте начнём поиск для другого автомобиля" in last_bot_reply:
            return False, ""
    
    # Проверка только по ключевым фразам
    reset_phrases = ["начать новый поиск", "новый поиск", "начать заново", "другая машина", "другое авто"]
    query_lower = query.lower().strip()
    
    for phrase in reset_phrases:
        if phrase in query_lower:
            return True, "Хорошо! Давайте начнём поиск для другого автомобиля. Напишите, какая запчасть вам нужна (например, «нужны тормозные колодки на Kia Rio»)."
    
    return False, ""
def generate_response_with_llm(car_info: dict, matches: list, part_name: str, found: bool) -> str:
    """Формирует ответ пользователю с помощью LLM (подробный промпт из первого кода)"""
    if not part_name or len(part_name) < 2:
        part_name = "запчасть"
    car_info_str = f"{car_info['brand']} {car_info['model']} {car_info['year']} г., {car_info['engine']} л"

    if found and matches:
        parts_list = "\n".join(matches)
        prompt = f"""
Ты — вежливый консультант интернет-магазина автозапчастей.
Пользователь искал: "{part_name}"
Для автомобиля: {car_info_str}
Найдены следующие запчасти:

{parts_list}

Сформируй вежливый, информативный ответ пользователю.
Сообщи, что найдено. Перечисли запчасти с артикулами.
В конце добавь: "Если хотите подобрать аналоги — просто скажите: «Аналоги на [артикул]»."
Также в конце добавь: "Если нужна запчасть на другой автомобиль, напишите: «начать новый поиск»."

Ответ должен быть кратким, но полезным.
"""
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=300
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"Ошибка генерации ответа: {e}")
            return (f"В моей базе для {car_info_str} найдено:\n\n{parts_list}\n\n"
                    "Если хотите подобрать аналоги — просто скажите: «Аналоги на [артикул]»."
                    "Если нужна запчасть на другой автомобиль, напишите: «начать новый поиск».")
    else:
        prompt = f"""
Ты — вежливый консультант интернет-магазина автозапчастей.
Пользователь искал: "{part_name}"
Для автомобиля: {car_info_str}

К сожалению, в каталоге не найдено подходящих запчастей.

Сформируй вежливый ответ, в котором:
1. Извинись, что не смог найти запчасть.
2. Попроси пользователя оставить номер телефона.
3. Пообещай, что специалист свяжется с ним для уточнения деталей.
4. Укажи формат ввода номера: +7 XXX XXX-XX-XX
5. В конце добавь: "Если нужна запчасть на другой автомобиль, напишите: «начать новый поиск»."

Ответ должен быть кратким, вежливым и понятным.
"""
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=200
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"Ошибка генерации ответа: {e}")
            return (f"🙏 Извините, я не смог найти {part_name} для {car_info_str}.\n\n"
                    "Пожалуйста, оставьте ваш номер телефона, и наш специалист свяжется с вами.\n\n"
                    "📞 Введите номер в формате: +7 XXX XXX-XX-XX\n"
                    "Если нужна запчасть на другой автомобиль, напишите: «начать новый поиск».")


def classify_intent(user_query: str, chat_history: list) -> str:
    context = " ".join([u for u, b in chat_history if u and isinstance(u, str)])
    prompt = f"""
Ты — маршрутизатор запросов в интернет-магазине автозапчастей. Твоя задача — определить ТОЧНЫЙ ТИП запроса.

Правила определения (строго по приоритету):

🔹 **ANALOG** — если в запросе ЕСТЬ артикул детали:
   - Артикул: комбинация букв и цифр, 5+ символов, обычно заглавные
   - Ключевые слова: "аналоги", "замена", "подойдет вместо", "cross"
   Примеры: "аналоги на TRW GDB1234", "что подойдет вместо BOSCH 0986471"

🔹 **SEARCH** — если пользователь ХОЧЕТ КУПИТЬ или ПОДОБРАТЬ запчасть:
   - Есть слова: "нужны", "нужен", "хочу", "купить", "подбери", "есть в наличии", "найди", "цену"
   - ИЛИ явно указана запчасть (колодки, фильтр, свечи, диск, масло, ремень, помпа, тормозные диски, тормозные колодки, свечи зажигания)
   - ИЛИ есть марка/модель авто в запросе
   - **ВАЖНО: "свечи зажигания", "тормозные колодки", "тормозные диски" — ЭТО НЕ ДИАГНОСТИКА! Это обычные запчасти для замены.**
   Примеры: "нужны колодки на Kia Rio", "свечи зажигания на Toyota", "мне нужны тормозные колодки"

🔹 **DIAGNOSE** — если пользователь ОПИСЫВАЕТ НЕИСПРАВНОСТЬ:
   - Есть симптомы: "стук", "скрежет", "вибрация", "запах", "дым", "перегрев", "не заводится"
   - Есть поведение: "при торможении", "на холостых", "на скорости", "при повороте"
   Примеры: "скрежет при торможении", "стук в подвеске"

🔹 **ESCALATE** — всё остальное:
   - "помогите", "оператор"
   - Или если запрос не подходит под другие категории

История диалога для контекста: "{context}"
Текущий запрос: "{user_query}"

Верни ТОЛЬКО одно слово: DIAGNOSE, SEARCH, ANALOG или ESCALATE.
"""
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=20
        )
        intent = resp.choices[0].message.content.strip().upper()
        for bad in ['"', "'", ".", ":"]:
            intent = intent.replace(bad, "").strip()
        intent = intent.split()[0] if intent.split() else ""
        if intent in ["DIAGNOSE", "SEARCH", "ANALOG", "ESCALATE"]:
            return intent
    except Exception as e:
        print(f"Ошибка classify_intent: {e}")

    # Fallback (как во втором коде, но с более широкими проверками)
    query = user_query.lower().strip()
    if re.search(r'[A-Z0-9]{5,}', user_query.upper()):
        return "ANALOG"
    if any(sym in query for sym in ["стук", "скрежет", "вибрац", "запах", "не заводит", "дым", "перегрев"]):
        return "DIAGNOSE"
    if any(w in query for w in ["нужн", "хочу", "куп", "подбери", "найди"]) and any(p in query for p in ["колодк", "фильтр", "свеч", "диск", "масло", "ремень", "помпа"]):
        return "SEARCH"
    return "ESCALATE"


# Агенты
def diagnose_agent(query: str, chat_history: list) -> tuple:  # changed: возвращаем tuple (str, bool)
    """Полноценный агент диагностики с отправкой уведомлений и выводом артикулов (как в первом коде)"""
    all_symptoms = [item["symptom"] for item in KNOWLEDGE_BASE] if KNOWLEDGE_BASE else []
    if not all_symptoms:
        # Если нет базы симптомов — отправляем уведомление и запрашиваем номер
        dialog_summary = "\n".join([f"👤 {u}\n🤖 {b}" for u, b in chat_history[-5:] if u or b])
        send_email_notification("Ожидание ввода номера", dialog_summary, "⚠️ База знаний пуста!")
        reply = ("Не удалось определить неисправность.\n\n"
                "Пожалуйста, оставьте ваш номер телефона, и наш специалист свяжется с вами.\n\n"
                "📞 Введите номер в формате: +7 XXX XXX-XX-XX")
        return reply, False   # changed: оценку не показываем

    # Поиск ближайшего симптома через LLM
    prompt = f"""
Ты — эксперт по диагностике неисправностей автомобилей. Твоя задача — найти ОДИН самый близкий по смыслу симптом из списка.

Правила:
- Игнорируй слова "у меня", "почему", "как устранить" — смотри только на суть неисправности.
- "Сильное торможение" = "интенсивное торможение"
- "Кочки" = "неровности"
- "Скрип при старте" = "скрип при начале движения"
- Если запрос содержит несколько симптомов — выбери главный.

Верни ТОЛЬКО полное название симптома из списка — дословно, без изменений, без кавычек.

Запрос: "{query}"

Список симптомов:
{chr(10).join(all_symptoms)}

Примеры:
"запах гари после сильного торможения" → "Запах гари после интенсивного торможения"
"стук на кочках" → "Стук в подвеске на неровностях"
"скрипит при трогании" → "Скрип при начале движения"

Ответ:
"""
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=60
        )
        matched_symptom = resp.choices[0].message.content.strip()
        if matched_symptom not in all_symptoms:
            matched_symptom = ""
    except Exception as e:
        print(f"Ошибка поиска симптома: {e}")
        matched_symptom = ""

    if not matched_symptom:
        # Симптом не найден — отправляем уведомление
        all_messages = []
        for u, b in chat_history[-5:]:
            if u:
                all_messages.append(f"👤 Клиент: {u}")
            if b:
                all_messages.append(f"🤖 Бот: {b}")
        all_messages.append(f"👤 Клиент: {query}")
        dialog_summary = "\n".join(all_messages)
        send_email_notification("Ожидание ввода номера", dialog_summary, "⚠️ Неисправность не найдена в базе знаний!")
        reply = ("Не удалось определить неисправность по вашему описанию.\n\n"
                "Пожалуйста, оставьте ваш номер телефона, и наш специалист свяжется с вами для уточнения проблемы.\n\n"
                "📞 Введите номер в формате: +7 XXX XXX-XX-XX")
        return reply, False   # changed: оценку не показываем

    # Ищем данные по найденному симптому
    kb_data = None
    for item in KNOWLEDGE_BASE:
        if item["symptom"] == matched_symptom:
            kb_data = item
            break

    if not kb_data or not kb_data.get("cause"):
        # Нашли симптом, но нет данных в базе
        all_messages = []
        for u, b in chat_history[-5:]:
            if u:
                all_messages.append(f"👤 Клиент: {u}")
            if b:
                all_messages.append(f"🤖 Бот: {b}")
        all_messages.append(f"👤 Клиент: {query}")
        dialog_summary = "\n".join(all_messages)
        send_email_notification("Ожидание ввода номера", dialog_summary, f"⚠️ По симптом '{matched_symptom}' нет данных в БД!")
        reply = (f"Найден симптом: {matched_symptom}\n\n"
                "К сожалению, в базе нет информации по этому симптому.\n"
                "Пожалуйста, оставьте ваш номер телефона, и наш специалист свяжется с вами.\n\n"
                "📞 Введите номер в формате: +7 XXX XXX-XX-XX")
        return reply, False   # changed: оценку не показываем

    # Формируем ответ с артикулами (examples)
    response = f"Симптом: {kb_data['symptom']}\nПричина: {kb_data['cause']}\nРекомендуемые запчасти: {', '.join(kb_data['parts'])}"
    if kb_data.get('examples'):
        response += f"\nВозможные артикулы: {kb_data['examples']}"
    response += "\n\nЕсли нужна запчасть на другой автомобиль, напишите: «начать новый поиск»."
    return response, True   # changed: успешная диагностика -> показываем оценку


def search_agent(query: str, chat_history: list) -> tuple:   # изменён тип возврата
    info = extract_car_info_with_llm(chat_history)

    if not (info["brand"] and info["model"] and info["year"] and info["engine"]):
        reply = "Пожалуйста, укажите марку, модель, год и объём двигателя — без этого я не могу подобрать запчасти."
        return reply, False   # неполные данные → оценку не показываем

    try:
        year = int(info["year"])
        engine = float(info["engine"])
    except ValueError:
        reply = "Не удалось распознать год или объём двигателя. Пример: «Kia Rio 2012 года, 1.4 л»."
        return reply, False   # ошибка распознавания → оценку не показываем

    if not CATALOG:
        reply = "База каталога запчастей пока не загружена."
        return reply, False   # нет каталога → оценку не показываем

    # Извлечение названия запчасти
    original_request = ""
    for u, b in chat_history:
        if u and any(word in u.lower() for word in ["нужен", "нужны", "хочу", "подбери", "найди"]):
            original_request = u
            break
    search_query = original_request if original_request else query
    part_name = extract_part_name_from_query(search_query, chat_history)
    if not part_name:
        part_name = query

    # Поиск в каталоге
    matches = []
    brand_clean = info["brand"].lower().strip()
    model_clean = info["model"].lower().strip()
    for item in CATALOG:
        try:
            if (item["brand"].lower() == brand_clean and
                item["model"].lower() == model_clean and
                item["year_start"] <= year <= item["year_end"] and
                abs(item["engine"] - engine) < 0.15):
                matches.append(f"{item['part_name']} — артикул: {item['part_number']}, цена: {item['price']} ₽")
        except Exception:
            continue

    # Фильтрация через LLM
    filtered = filter_matches_with_llm(part_name, matches, info)
    found = len(filtered) > 0

    # Отправка уведомления, если ничего не найдено
    if not found:
        all_messages = []
        for u, b in chat_history:
            if u:
                all_messages.append(f"👤 Клиент: {u}")
            if b:
                all_messages.append(f"🤖 Бот: {b}")
        all_messages.append(f"👤 Клиент: {search_query}")
        all_messages.append(f"🤖 Бот: [Запчасть '{part_name}' не найдена для {info['brand']} {info['model']} {info['year']} г., {info['engine']} л]")
        dialog_summary = "\n".join(all_messages[-10:])
        send_email_notification("Ожидание ввода номера", dialog_summary, "⚠️ Запчасть не найдена в каталоге!")

    reply_text = generate_response_with_llm(info, filtered, part_name, found)
    return reply_text, found   # found = True → оценку показываем, иначе False


def analog_agent_message(query: str, chat_history: list) -> tuple:   # изменён возвращаемый тип
    part = extract_part_number(query)
    if not part or len(part) < 5:
        reply = ("🔍 Пожалуйста, напишите номер запчасти, для которой нужно подобрать аналог (артикул должен содержать 5 и более символов).\n\n"
                 "Пример: «Аналоги на TRW GDB1234»")
        return reply, False   # оценку не показываем
    analogs = find_analogs(part)
    if analogs:
    # Разбиваем строку аналогов по запятой с пробелом (возможно, у вас разделитель ', ')
        analogs_list = analogs.split(', ')
        # Формируем маркированный список: каждый элемент с новой строки и символом •
        analogs_formatted = '\n'.join([f"• {item}" for item in analogs_list])
        reply = (f"🔧 Аналоги для артикула {part}:\n{analogs_formatted}\n\n"
             "Если нужна запчасть на другой автомобиль, напишите: «начать новый поиск».")
        return reply, True
    else:
        # Отправляем уведомление
        all_messages = []
        for u, b in chat_history[-5:]:
            if u:
                all_messages.append(f"👤 Клиент: {u}")
            if b:
                all_messages.append(f"🤖 Бот: {b}")
        all_messages.append(f"👤 Клиент: {query}")
        dialog_summary = "\n".join(all_messages)
        send_email_notification("Ожидание ввода номера", dialog_summary, f"⚠️ Аналоги для артикула {part} не найдены!")
        reply = (f"Извините, аналоги для артикула {part} не найдены в базе.\n\n"
                 "Пожалуйста, оставьте ваш номер телефона, и наш специалист поможет подобрать аналог.\n\n"
                 "📞 Введите номер в формате: +7 XXX XXX-XX-XX\n"
                 "Если нужна запчасть на другой автомобиль, напишите: «начать новый поиск».")
        return reply, False   # не найдены → оценку не показываем

def extract_phone_number(text: str) -> str:
    phone_pattern = r'(\+7|8)?[\s\-]?\(?(\d{3})\)?[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})'
    match = re.search(phone_pattern, text)
    if match:
        digits = re.sub(r'\D', '', text)
        if len(digits) == 11 and digits.startswith('8'):
            digits = '+7' + digits[1:]
        elif len(digits) == 10:
            digits = '+7' + digits
        return digits
    return None


def ask_phone_number_and_escalate(chat_history: list) -> tuple:
    reply = ("🙏 Извините, я не смог решить ваш вопрос.\n\n"
             "Пожалуйста, оставьте ваш номер телефона, и наш оператор свяжется с вами в ближайшее время.\n\n"
             "📞 Введите номер в формате: +7 XXX XXX-XX-XX\n"
             "Если нужна запчасть на другой автомобиль, напишите: «начать новый поиск».")
    return reply, False

def chat_with_ai(new_message: str, chat_history: list) -> tuple:
    if chat_history is None:
        chat_history = []

    # Проверка команды сброса поиска
    is_reset, reset_msg = check_reset_with_llm(new_message, chat_history)
    if is_reset:
        new_history = chat_history + [(new_message, reset_msg)]
        return new_history, reset_msg, False

    # Уточнение типа запчасти
    clarification = clarify_part_type_with_llm(new_message, chat_history)
    if clarification:
        new_history = chat_history + [(new_message, clarification)]
        return new_history, clarification, False

    # Обработка ожидания номера телефона
    waiting_for_phone = False
    if chat_history and len(chat_history) > 0:
        last_bot_reply = chat_history[-1][1]
        if last_bot_reply and "номер телефона" in last_bot_reply.lower():
            waiting_for_phone = True

    if waiting_for_phone:
        phone = extract_phone_number(new_message)
        if phone:
            all_messages = []
            for u, b in chat_history:
                if u:
                    all_messages.append(f"👤 Клиент: {u}")
                if b and "номер телефона" not in b.lower() and "Не удалось распознать номер" not in b:
                    all_messages.append(f"🤖 Бот: {b}")
            all_messages.append(f"👤 Клиент: {new_message}")
            success_reply = f"✅ Спасибо! Ваш номер {phone} передан оператору. Свяжемся с вами в ближайшее время."
            all_messages.append(f"🤖 Бот: {success_reply}")
            dialog_summary = "\n".join(all_messages[-15:])
            send_email_notification(phone, dialog_summary, "Новый запрос от клиента")
            new_history = chat_history + [(new_message, success_reply)]
            return new_history, success_reply, False
        else:
            reply = "Не удалось распознать номер. Пожалуйста, введите номер телефона в формате: +7 XXX XXX-XX-XX"
            new_history = chat_history + [(new_message, reply)]
            return new_history, reply, False

    # Основная классификация интента
    last_bot_msg = chat_history[-1][1] if chat_history and len(chat_history[-1]) > 1 else ""
    if last_bot_msg and any(phrase in last_bot_msg.lower() for phrase in [
        "какой марки", "какая модель", "какого года", "объём двигателя",
        "марку автомобиля", "модель автомобиля", "года выпуска", "двигателя"
    ]):
        intent = "SEARCH"
    else:
        intent = classify_intent(new_message, chat_history)

    # Если пользователь ищет аналоги, но не указал артикул
    analog_keywords = ["аналоги", "замена", "подойдет вместо", "cross", "аналог"]
    if any(kw in new_message.lower() for kw in analog_keywords):
        part = extract_part_number(new_message)
        if not part or len(part) < 5:
            reply = "🔍 Пожалуйста, напишите номер запчасти, для которой нужно подобрать аналог (артикул должен содержать 5 и более символов).\n\nПример: «Аналоги на TRW GDB1234»"
            new_history = chat_history + [(new_message, reply)]
            return new_history, reply, False

    # Обработка SEARCH с уточнением недостающих параметров
    if intent == "SEARCH":
        # Проверка невалидного года при ответе на вопрос
        if last_bot_msg and "Какого года" in last_bot_msg:
            year_match = re.search(r'\b(\d{4})\b', new_message)
            if year_match:
                year = int(year_match.group())
                if year > 2026:
                    error_msg = "Год выпуска автомобиля не может быть больше 2026. Пожалуйста, укажите корректный год (2026 или ранее)."
                    new_history = chat_history + [(new_message, error_msg)]
                    return new_history, error_msg, False
                elif year < 1950:
                    error_msg = "Год выпуска автомобиля не может быть меньше 1950. Пожалуйста, укажите корректный год."
                    new_history = chat_history + [(new_message, error_msg)]
                    return new_history, error_msg, False

        info = extract_car_info_with_llm(chat_history + [(new_message, "")])

        # Проверяем, каких данных не хватает
        missing_field = None
        if not info.get("brand"):
            missing_field = "brand"
        elif not info.get("model"):
            missing_field = "model"
        elif not info.get("year"):
            missing_field = "year"
        elif not info.get("engine"):
            missing_field = "engine"

        if missing_field:
            questions = {
                "brand": "Какой марки у вас автомобиль?",
                "model": "Какая модель автомобиля?",
                "year": "Какого года выпуска автомобиль?",
                "engine": "Уточните объём двигателя (например, 1.4 л или 1.6 л)."
            }
            question = questions[missing_field]
            new_history = chat_history + [(new_message, question)]
            return new_history, question, False

        # Если все данные есть, но engine пустой (страховка)
        if not info.get("engine"):
            reply = "Уточните объём двигателя (например, 1.4 л или 1.6 л)."
            new_history = chat_history + [(new_message, reply)]
            return new_history, reply, False

    # ========== ОСНОВНАЯ ОБРАБОТКА С return для всех веток ==========
    current_history = chat_history + [(new_message, "")]
    
    # ИСПРАВЛЕНИЕ: Добавляем return для всех веток
    if intent == "DIAGNOSE":
        reply, show_feedback = diagnose_agent(new_message, current_history)
        new_history = chat_history + [(new_message, reply)]
        return new_history, reply, show_feedback  # ✅ ДОБАВЛЕНО!
        
    elif intent == "SEARCH":
        reply, show_feedback = search_agent(new_message, current_history)
        new_history = chat_history + [(new_message, reply)]
        return new_history, reply, show_feedback  # ✅ ДОБАВЛЕНО!
        
    elif intent == "ANALOG":
        reply, show_feedback = analog_agent_message(new_message, chat_history)
        new_history = chat_history + [(new_message, reply)]
        return new_history, reply, show_feedback
        
    else:  # ESCALATE
        all_messages = []
        for u, b in chat_history:
            if u:
                all_messages.append(f"👤 Клиент: {u}")
            if b:
                all_messages.append(f"🤖 Бот: {b}")
        all_messages.append(f"👤 Клиент: {new_message}")
        dialog_summary = "\n".join(all_messages[-8:])
        send_email_notification("Ожидание ввода номера", dialog_summary, "⚠️ Чат-бот не справился с запросом!")
        reply, show_feedback = ask_phone_number_and_escalate(chat_history)
        new_history = chat_history + [(new_message, reply)]
        return new_history, reply, show_feedback


import shutil
from datetime import datetime

# Конфигурация папок
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
KB_FOLDER = os.path.join(os.path.dirname(__file__), "kb")
ARCHIVE_FOLDER = os.path.join(os.path.dirname(__file__), "kb_archive")

# Обязательные колонки и разделители для двух файлов
FILE_CONFIG = {
    "catalog.csv": {
        "required_columns": ["brand", "model", "year_start", "year_end", "engine", "part_name", "part_number", "price"],
        "delimiter": ","
    },
    "analogs_db.csv": {
        "required_columns": ["MODEL", "PART_NUMBER", "ANALOG1", "PRICE1", "ANALOG2", "PRICE2"],
        "delimiter": ";"
    }
}

def validate_csv(filepath: str, file_type: str) -> bool:
    """Проверяет наличие файла, структуру колонок и базовые типы данных."""
    if not os.path.exists(filepath):
        print(f"Файл {filepath} не найден")
        return False
    if not filepath.endswith(".csv"):
        print(f"Файл {filepath} не является CSV")
        return False
    config = FILE_CONFIG.get(file_type)
    if not config:
        print(f"Неизвестный тип файла {file_type}")
        return False
    required = config["required_columns"]
    delimiter = config["delimiter"]
    
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            headers = reader.fieldnames
            if not headers:
                print(f"Файл {file_type} не содержит заголовков")
                return False
            missing = set(required) - set(headers)
            if missing:
                print(f"В файле {file_type} отсутствуют колонки: {missing}")
                return False
            # Проверка первой строки данных на корректность типов
            for row in reader:
                if file_type == "catalog.csv":
                    try:
                        int(row["year_start"])
                        int(row["year_end"])
                        float(row["engine"])
                        int(row["price"])
                    except (ValueError, KeyError) as e:
                        print(f"Ошибка данных в {file_type}: {e}")
                        return False
                elif file_type == "analogs_db.csv":
                    if not row.get("PART_NUMBER", "").strip():
                        print(f"В {file_type} пустой PART_NUMBER")
                        return False
                break  # проверяем только первую строку
    except Exception as e:
        print(f"Ошибка при чтении {filepath}: {e}")
        return False
    return True

def archive_current_files():
    """Копирует текущие файлы catalog.csv и analogs_db.csv в архив с датой-временем."""
    os.makedirs(ARCHIVE_FOLDER, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for filename in ["catalog.csv", "analogs_db.csv"]:
        src = os.path.join(KB_FOLDER, filename)
        if os.path.exists(src):
            dst = os.path.join(ARCHIVE_FOLDER, f"{timestamp}_{filename}")
            shutil.copy2(src, dst)
    print(f"Архивированы файлы в {ARCHIVE_FOLDER}")

def update_knowledge_bases():
    """Проверяет загруженные файлы в UPLOAD_FOLDER и, если валидны, заменяет рабочие."""
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)   # убедимся, что папка существует
    results = {}
    all_valid = True
    
    for filename in ["catalog.csv", "analogs_db.csv"]:
        file_type = filename
        upload_path = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(upload_path):
            results[filename] = "Файл не найден в uploads/"
            all_valid = False
            continue
        if validate_csv(upload_path, file_type):
            results[filename] = "OK"
        else:
            results[filename] = "Ошибка валидации"
            all_valid = False
    
    if not all_valid:
        return results
    
    # Архивация текущих версий
    archive_current_files()
    
    # Замена файлов: перемещаем новые в KB_FOLDER
    for filename in ["catalog.csv", "analogs_db.csv"]:
        src = os.path.join(UPLOAD_FOLDER, filename)
        dst = os.path.join(KB_FOLDER, filename)
        shutil.move(src, dst)   # перемещаем (заменяет старый)
    
    # Перезагрузка глобальных переменных
    global CATALOG, ANALOGS_DB
    CATALOG = load_catalog(os.path.join(KB_FOLDER, "catalog.csv"))
    ANALOGS_DB = load_analogs_db(os.path.join(KB_FOLDER, "analogs_db.csv"))
    # База знаний (KNOWLEDGE_BASE) не перезагружается, она обновляется вручную
    
    print("✅ Каталог и база аналогов обновлены")
    results["status"] = "success"
    return results

# Запрос на обновление баз знаний
@app.route('/admin/update_kb', methods=['POST'])
def admin_update_kb():
    secret_token = request.headers.get('X-Admin-Token')
    if secret_token != "admin":   # секретный токен
        return jsonify({"error": "Unauthorized"}), 401
    result = update_knowledge_bases()
    if result.get("status") == "success":
        return jsonify({"message": "Базы обновлены", "details": result}), 200
    else:
        return jsonify({"error": "Ошибка валидации", "details": result}), 400

# Flask маршруты
chat_storage = {}

@app.route('/')
def index():
    return render_template('index.html')

# История диалога и время
@app.route('/ask', methods=['POST'])
def ask():
    start_time = time.time()
    data = request.get_json()
    user_message = data.get('message', '')
    session_id = data.get('session_id', 'default')
    if not user_message:
        return jsonify({'reply': 'Пожалуйста, напишите вопрос.', 'show_feedback': False})
    if session_id not in chat_storage:
        chat_storage[session_id] = []
    chat_history = chat_storage[session_id]

    # Распаковываем три значения, которые возвращает chat_with_ai
    updated_history, reply_text, show_feedback = chat_with_ai(user_message, chat_history)
    chat_storage[session_id] = updated_history

    end_time = time.time()
    response_time_ms = round((end_time - start_time) * 1000)
    # Логируем – передаём строку reply_text
    log_dialog(session_id, user_message, reply_text, response_time_ms)

    return jsonify({'reply': reply_text, 'show_feedback': show_feedback})

# Оценка обратной связи
@app.route('/feedback', methods=['POST'])
def feedback():
    data = request.get_json()
    rating = data.get('rating')        # 'positive' или 'negative'
    reply = data.get('reply', '')
    session_id = data.get('session_id', 'default')
    # Сохраняем в CSV-файл обратной связи
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    filepath = os.path.join(log_dir, "feedback.csv")
    file_exists = os.path.isfile(filepath)
    with open(filepath, "a", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "session_id", "reply_preview", "rating"])
        writer.writerow([
            datetime.now().isoformat(),
            session_id,
            reply[:200].replace("\n", " ").replace(",", ";"),
            rating
        ])
    return jsonify({'status': 'ok'})

@app.route('/clear', methods=['POST'])
def clear():
    session_id = request.get_json().get('session_id', 'default')
    if session_id in chat_storage:
        chat_storage[session_id] = []
    return jsonify({'status': 'ok'})

@app.route('/chat')
def chat():
    return render_template('chat.html')

# =============
# ВРЕМЕННЫЕ МАРШРУТЫ ДЛЯ СКАЧИВАНИЯ ЛОГОВ
# =============

@app.route('/download/dialogs')
def download_dialogs():
    """Временный маршрут для просмотра логов диалогов"""
    import os
    filepath = os.path.join(os.path.dirname(__file__), "logs", "dialogs.csv")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        # Возвращаем как текст с сохранением форматирования
        return f"<pre>{content}</pre>"
    return "Файл dialogs.csv не найден. Возможно, ещё не было диалогов."

@app.route('/download/feedback')
def download_feedback():
    """Временный маршрут для просмотра логов обратной связи"""
    import os
    filepath = os.path.join(os.path.dirname(__file__), "logs", "feedback.csv")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return f"<pre>{content}</pre>"
    return "Файл feedback.csv не найден. Возможно, ещё не было оценок."

if __name__ == '__main__':
    pass