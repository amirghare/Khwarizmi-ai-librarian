from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
import config
from book_embedder import BookEmbedder
from thesis_details import ThesisDetailsLoader
from collections import defaultdict
from datetime import datetime, timedelta
import re

print("🔄 Loading modules...")

last_shown_results = defaultdict(list)
openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
embedder = None
thesis_details_loader = None
conversation_memory = defaultdict(list)
search_results_memory = defaultdict(list)
last_message_time = defaultdict(lambda: datetime.now())
last_query_memory = defaultdict(str)

# ✅ Filter system
filter_state = defaultdict(lambda: {
    'active': False,
    'stage': None,
    'last_offer': None
})

ORIGINAL_EXCEL_PATH = "output/theses/theses_normalized.xlsx"
FAISS_INDEX_PATH = "output/theses/faiss_index.bin"

SYSTEM_PROMPT = """
شما یک دستیار هوشمند کتابخانه دانشگاه خوارزمی هستید.
**قوانین مهم:**
1. **فقط از پایان‌نامه‌های ارائه شده استفاده کنید**
2. **نحوه پاسخ:**
   a) جستجوی اولیه: تمام پایان‌نامه‌ها را معرفی کنید
   b) درخواست بیشتر: فقط پایان‌نامه‌های جدید
3. **فرمت:**
   📄 «عنوان»
      پژوهشگر: ...
      استاد راهنما: ...
      مقطع: ...
      رشته: ...
      سال: ...
4. **زبان**: فارسی، دوستانه، مختصر
5. **ممنوعیت‌ها:**
   - "پایان‌نامه‌ای نداریم" نگو
   - پایان‌نامه تکراری معرفی نکن
"""


def format_field(field_raw):
    if not field_raw or str(field_raw).lower() in ['nan', 'none', '']:
        return None
    value = str(field_raw).strip()
    if 'nan' in value.lower():
        return None
    return value


def clean_text_for_display(text):
    if not text:
        return "نامشخص"
    text = str(text).strip()
    if text.lower() in ['nan', 'none', '']:
        return "نامشخص"
    text = re.sub(r'\bnan\b', 'نامشخص', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text if text else "نامشخص"


def enrich_search_result(result):
    if thesis_details_loader is None:
        return result
    row_id = result.get('رديف')
    if not row_id:
        return result
    details = thesis_details_loader.get_thesis_details(row_id)
    if details:
        enriched = result.copy()
        enriched.update(details)
        return enriched
    return result


# Memory functions
def clean_old_conversations():
    current_time = datetime.now()
    expired_chats = []
    for chat_id, last_time in last_message_time.items():
        if current_time - last_time > timedelta(days=7):
            expired_chats.append(chat_id)
    for chat_id in expired_chats:
        conversation_memory.pop(chat_id, None)
        search_results_memory.pop(chat_id, None)
        last_message_time.pop(chat_id, None)
        last_query_memory.pop(chat_id, None)
        last_shown_results.pop(chat_id, None)
        filter_state.pop(chat_id, None)


def add_to_conversation(chat_id, role, content):
    conversation_memory[chat_id].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now()
    })
    current_time = datetime.now()
    three_days_ago = current_time - timedelta(days=3)
    conversation_memory[chat_id] = [
        msg for msg in conversation_memory[chat_id]
        if msg["timestamp"] > three_days_ago
    ]
    if len(conversation_memory[chat_id]) > 100:
        conversation_memory[chat_id] = conversation_memory[chat_id][-100:]
    last_message_time[chat_id] = datetime.now()


def save_search_results(chat_id, results, query=""):
    search_results_memory[chat_id] = results
    if query:
        last_query_memory[chat_id] = query
    last_message_time[chat_id] = datetime.now()


def get_last_search_results(chat_id):
    return search_results_memory.get(chat_id, [])


def get_last_query(chat_id):
    return last_query_memory.get(chat_id, "")


# Filter system
def reset_filter_state(chat_id):
    filter_state[chat_id] = {
        'active': False,
        'stage': None,
        'last_offer': None
    }


def should_offer_filter(chat_id, search_results, is_new_search=False):
    if not is_new_search or not search_results or len(search_results) <= 1:
        return False
    last_offer = filter_state[chat_id].get('last_offer')
    if last_offer:
        time_diff = (datetime.now() - last_offer).total_seconds()
        if time_diff < 30:
            return False
    return True


def is_filter_command(message):
    filter_keywords = ['📅', '🎓', '👨‍🏫', '📚', '❌', '🔙', 'فیلتر', 'بله', 'آره', 'خیر', 'نه']
    message_lower = message.lower()
    return any(kw in message_lower or kw in message for kw in filter_keywords)


def apply_filters(results, filter_type, filter_value):
    if not results:
        return []
    filtered = []
    for r in results:
        if filter_type == 'سال':
            year = format_field(r.get('سال')) or format_field(r.get('سال دفاع'))
            if year and filter_value in str(year):
                filtered.append(r)
        elif filter_type == 'استاد راهنما':
            advisor = format_field(r.get('استاد راهنما'))
            co_advisor = format_field(r.get('استاد مشاور'))
            filter_lower = filter_value.lower()
            if (advisor and filter_lower in advisor.lower()) or (co_advisor and filter_lower in co_advisor.lower()):
                filtered.append(r)
        elif filter_type == 'مقطع':
            degree = format_field(r.get('مقطع'))
            if degree:
                degree_lower = degree.lower()
                filter_lower = filter_value.lower()
                if (filter_lower in ['دکتر', 'دکتری', 'دکترا', 'phd'] and ('دكتر' in degree_lower or 'دکتر' in degree_lower)) or \
                   (filter_lower in ['کارشناسی ارشد', 'ارشد'] and 'ارشد' in degree_lower) or \
                   (filter_value.lower() in degree_lower):
                    filtered.append(r)
        elif filter_type == 'رشته':
            field = format_field(r.get('رشته')) or format_field(r.get('رشته تحصیلی'))
            if field and filter_value.lower() in field.lower():
                filtered.append(r)
    return filtered


def get_available_filters(results, chat_id=None):
    # 1) Priority: Results actually displayed
    if chat_id:
        shown_results = last_shown_results.get(chat_id, [])
    else:
        shown_results = []

    # 2) If nothing was displayed → same input results (but only 6)
    if not shown_results:
        shown_results = results[:6]

    # 3) If it still wasn't there → it means there is nothing to filter
    if not shown_results:
        return {'years':[], 'advisors':[], 'degrees':[], 'fields':[]}

    years, advisors, degrees, fields = set(), set(), set(), set()

    for r in shown_results:
        # Year
        year = format_field(r.get('سال')) or format_field(r.get('سال دفاع'))
        if year:
            years.add(year)

        # Advisor
        advisor = format_field(r.get('استاد راهنما'))
        if advisor:
            advisors.add(advisor)

        # ِDegree
        degree = format_field(r.get('مقطع'))
        if degree:
            degrees.add(degree)

        # Major
        field = format_field(r.get('رشته')) or format_field(r.get('رشته تحصیلی'))
        if field:
            fields.add(field)

    return {
        'years': sorted(list(years), reverse=True),
        'advisors': sorted(list(advisors)),
        'degrees': sorted(list(degrees)),
        'fields': sorted(list(fields)),
    }


def create_filter_menu_keyboard():
    return ReplyKeyboardMarkup([
        ["📅 فیلتر بر اساس سال", "🎓 فیلتر بر اساس مقطع"],
        ["👨‍🏫 فیلتر بر اساس استاد راهنما", "📚 فیلتر بر اساس رشته"],
        ["❌ انصراف"]
    ], resize_keyboard=True, one_time_keyboard=True)


def handle_filter_interaction(user_message, chat_id):
    query_lower = user_message.lower()
    current_stage = filter_state[chat_id].get('stage')

    if current_stage == 'ask':
        if query_lower.startswith('ب') or query_lower.startswith('y') or query_lower.startswith('Y') or 'آره' in query_lower:
            filter_state[chat_id].update({'active': True, 'stage': 'menu'})
            return ("لطفاً نوع فیلتر را انتخاب کنید:", create_filter_menu_keyboard(), False)
        elif query_lower.startswith('ن') or query_lower.startswith('خ') or query_lower.startswith('n') or query_lower.startswith('N') or user_message == "❌ انصراف":
            reset_filter_state(chat_id)
            return ("باشه! 👍", ReplyKeyboardRemove(), False)
        else:
            reset_filter_state(chat_id)
            return (None, None, False)

    elif current_stage == 'menu':
        shown_results = last_shown_results.get(chat_id, [])
        if not shown_results:
            reset_filter_state(chat_id)
            return ("متأسفم، نتایج قبلی پیدا نشد.", ReplyKeyboardRemove(), False)

        available_filters = get_available_filters(shown_results, chat_id)

        if user_message == "📅 فیلتر بر اساس سال" and available_filters['years']:
            keyboard = [available_filters['years'][i:i+3] for i in range(0, len(available_filters['years']), 3)]
            keyboard.append(["🔙 بازگشت", "❌ انصراف"])
            filter_state[chat_id]['stage'] = 'year'
            return ("لطفاً سال را انتخاب کنید:", ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True), False)

        elif user_message == "🎓 فیلتر بر اساس مقطع" and available_filters['degrees']:
            keyboard = [[d] for d in available_filters['degrees']] + [["🔙 بازگشت", "❌ انصراف"]]
            filter_state[chat_id]['stage'] = 'degree'
            return ("لطفاً مقطع را انتخاب کنید:", ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True), False)

        elif user_message == "👨‍🏫 فیلتر بر اساس استاد راهنما" and available_filters['advisors']:
            keyboard = [[adv] for adv in available_filters['advisors']] + [["🔙 بازگشت", "❌ انصراف"]]
            filter_state[chat_id]['stage'] = 'advisor'
            return ("لطفاً استاد راهنما را انتخاب کنید:", ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True), False)

        elif user_message == "📚 فیلتر بر اساس رشته" and available_filters['fields']:
            keyboard = [[f] for f in available_filters['fields']] + [["🔙 بازگشت", "❌ انصراف"]]
            filter_state[chat_id]['stage'] = 'field'
            return ("لطفاً رشته را انتخاب کنید:", ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True), False)

        elif user_message == "❌ انصراف":
            reset_filter_state(chat_id)
            return ("باشه! 👍", ReplyKeyboardRemove(), False)
        else:
            reset_filter_state(chat_id)
            return (None, None, False)

    elif current_stage in ['year', 'degree', 'advisor', 'field']:
        if user_message == "🔙 بازگشت":
            filter_state[chat_id]['stage'] = 'menu'
            return ("لطفاً نوع فیلتر را انتخاب کنید:", create_filter_menu_keyboard(), False)
        elif user_message == "❌ انصراف":
            reset_filter_state(chat_id)
            return ("باشه! 👍", ReplyKeyboardRemove(), False)
        else:
            prev_results = get_last_search_results(chat_id)
            filter_type_map = {'year': 'سال', 'degree': 'مقطع', 'advisor': 'استاد راهنما', 'field': 'رشته'}
            filter_type = filter_type_map.get(current_stage)
            filtered = apply_filters(prev_results, filter_type, user_message)

            if filtered:
                save_search_results(chat_id, filtered, f"فیلتر {filter_type} {user_message}")
                last_shown_results[chat_id] = filtered[:6]
                reset_filter_state(chat_id)
                filter_name_map = {
                    'سال': f"سال {user_message}",
                    'مقطع': f"مقطع {user_message}",
                    'استاد راهنما': f"استاد راهنما «{user_message}»",
                    'رشته': f"رشته «{user_message}»"
                }
                return (f"✅ {len(filtered)} پایان‌نامه برای {filter_name_map[filter_type]} پیدا شد.", ReplyKeyboardRemove(), True)
            else:
                reset_filter_state(chat_id)
                return (f"متأسفم، هیچ پایان‌نامه‌ای برای {user_message} پیدا نکردم.", ReplyKeyboardRemove(), False)

    reset_filter_state(chat_id)
    return ("متأسفم، متوجه نشدم.", ReplyKeyboardRemove(), False)


# RAG
def initialize_embedder():
    global embedder, thesis_details_loader
    print("🔄 Loading FAISS index...")
    try:
        embedder = BookEmbedder(api_key=config.OPENAI_API_KEY)
        embedder.load_index(FAISS_INDEX_PATH)
        print("✅ FAISS index loaded")
    except Exception as e:
        print(f"❌ Error loading index: {e}")
        return False
    print("🔄 Loading thesis details...")
    try:
        thesis_details_loader = ThesisDetailsLoader(ORIGINAL_EXCEL_PATH)
        print("✅ Thesis details loaded")
    except Exception as e:
        print(f"❌ Error loading details: {e}")
        return False
    return True


def is_followup_question(query, chat_id):
    followup_keywords = ['بله', 'آره', 'اوکی', 'باشه', 'بیشتر', 'جدیدتر', 'بهترین', 'کدوم', 'اولی', 'دومی', 'اون', 'این', 'همون', 'باز', 'دوباره', 'معرفی کن', 'شرح بده', 'استاد راهنما', 'پژوهشگر']
    query_lower = query.lower()
    if is_filter_command(query):
        return False
    return any(kw in query_lower for kw in followup_keywords) and len(get_last_search_results(chat_id)) > 0 and len(query.split()) <= 10


def filter_results_with_gpt(user_query, search_results, original_query=""):
    if not search_results:
        return []
    items_text = "\n".join([f"{i}. «{r.get('عنوان') or r.get('عنوان پایان‌نامه', '')}» - پژوهشگر: {r.get('نویسنده', '')}" for i, r in enumerate(search_results, 1)])
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"سوال: \"{user_query}\"\nموضوع اصلی: \"{original_query}\"\n\nلیست پایان‌نامه‌ها:\n{items_text}\n\nفقط مرتبط‌ها را انتخاب کن.\nخروجی: شماره‌ها با کاما (مثل '1,3') یا 'هیچکدام'."}],
            max_tokens=100,
            temperature=0.1
        )
        answer = response.choices[0].message.content.strip()
        if "هیچکدام" in answer.lower():
            return []
        numbers = [int(n) for n in re.findall(r'\b\d+\b', answer) if 1 <= int(n) <= len(search_results)]
        filtered = [search_results[n-1] for n in set(numbers)]
        print(f"🔍 GPT Filter: {len(filtered)}/{len(search_results)} related")
        return filtered if len(filtered) >= 2 else search_results[:5]
    except Exception as e:
        print(f"⚠️ Error in filter: {e}")
        return search_results[:5]


def search_by_advisor_direct(advisor_name, exclude_rows=None):
    if thesis_details_loader is None:
        return []
    try:
        results = []
        advisor_normalized = re.sub(r'\s+', ' ', advisor_name.lower().strip())
        for idx, row in thesis_details_loader.df.iterrows():
            advisor = format_field(row.get('استاد راهنما', ''))
            co_advisor = format_field(row.get('استاد مشاور', ''))
            match = False
            if advisor:
                advisor_clean = re.sub(r'\s+', ' ', advisor.lower().strip())
                if advisor_normalized in advisor_clean or advisor_clean in advisor_normalized:
                    match = True
            if not match and co_advisor:
                co_advisor_clean = re.sub(r'\s+', ' ', co_advisor.lower().strip())
                if advisor_normalized in co_advisor_clean or co_advisor_clean in advisor_normalized:
                    match = True
            if match:
                row_id = row.get('رديف')
                if exclude_rows is None or row_id not in exclude_rows:
                    result = row.to_dict()
                    result['distance'] = 0.1
                    results.append(result)
        print(f"🔍 Direct advisor search: {advisor_name} → {len(results)} result")
        return results[:10]
    except Exception as e:
        print(f"❌ Error in direct search: {e}")
        return []


def search_theses(query, k=None, distance_threshold=0.8, exclude_rows=None):
    if embedder is None:
        return []
    for pattern in [r'استاد راهنما[یش]*\s+(.+)', r'استاد\s+(.+)', r'راهنما[یش]*\s+(.+)']:
        if match := re.search(pattern, query, re.IGNORECASE):
            advisor_name = re.sub(r'(آن|که|باشه|باشد|بده|هست|است)', '', match.group(1).strip(), flags=re.IGNORECASE).strip()
            if advisor_name and len(advisor_name) > 3:
                print(f"   📌 Extracted Advisor: {advisor_name}")
                if direct_results := search_by_advisor_direct(advisor_name, exclude_rows):
                    return direct_results
    try:
        results = embedder.search(query, k=k or 30)
        enriched_results = [enriched for r in results if (enriched := enrich_search_result(r))['distance'] < distance_threshold and (exclude_rows is None or enriched['رديف'] not in exclude_rows)]
        print(f"📊 Search: '{query[:50]}...' → {len(enriched_results)} result")
        return enriched_results[:k] if k else enriched_results[:10]
    except Exception as e:
        print(f"❌ Error in search: {e}")
        return []


def generate_rag_response(user_query, chat_id):
    clean_old_conversations()

    if any(g in user_query.lower() for g in ['سلام', 'درود', 'hello', 'hi']) and len(user_query.split()) <= 3:
        return ("سلام! 👋\n\nمثال: پایان نامه یادگیری ماشین", False)

    is_followup = is_followup_question(user_query, chat_id)
    query_lower = user_query.lower()

    asking_author_patterns = [
        r'(پژوهشگر|نویسنده|استاد راهنما)\s+(پایان.?نامه\s+)?(اول|دوم|سوم|آخر|۱|۲|۳|1|2|3)ی?\s*(کیه|چیه|چیست|کدومه)?',
        r'(اول|دوم|سوم|آخر|۱|۲|۳|1|2|3)ی?\s+(پژوهشگر|نویسنده|استاد راهنما)\s*اش?\s*(کیه|چیه|چیست|کدومه)?',
        r'استاد راهنما\s*اش?\s+(کیه|چیه|چیست)',
        r'(پژوهشگر|نویسنده)\s*اش?\s+(کیه|چیه|چیست)',
    ]

    if any(re.search(p, query_lower) for p in asking_author_patterns) and 'معرفی' not in query_lower and 'بیشتر' not in query_lower and 'فیلتر' not in query_lower and len(user_query.split()) <= 10:
        print("📝 Researcher/Advisor Question")
        if not (shown_results := last_shown_results.get(chat_id, [])):
            return ("متأسفم، هنوز پایان‌نامه‌ای معرفی نکردم.", False)

        position = 0 if any(x in query_lower for x in ['اول', '۱', '1']) else (1 if any(x in query_lower for x in ['دوم', '۲', '2']) else (2 if any(x in query_lower for x in ['سوم', '۳', '3']) else -1))
        if position >= len(shown_results):
            return (f"متأسفم، من فقط {len(shown_results)} پایان‌نامه معرفی کردم.", False)

        target_item = shown_results[position]
        title = target_item.get('عنوان') or target_item.get('عنوان پایان‌نامه', '')
        person_type = "استاد راهنما" if 'استاد راهنما' in query_lower else "پژوهشگر"
        person = target_item.get('استاد راهنما' if person_type == "استاد راهنما" else 'نویسنده', '').strip()

        if not person or person.lower() in ['nan', 'none', '']:
            return (f"متأسفم، {person_type} پایان‌نامه «{title}» در سیستم ثبت نشده است.", False)
        return (f"{person_type} پایان‌نامه «{title}»، «{person}» است.", False)

    author_search_done = False
    if is_followup and any(kw in query_lower for kw in ['از این استاد', 'از استاد', 'پایان نامه های این استاد', 'پایان نامه دیگه از', 'از این پژوهشگر']):
        print("📚 Researcher/Advisor Search")
        if prev_results := last_shown_results.get(chat_id, get_last_search_results(chat_id)):
            target_item = prev_results[0] if 'اول' in query_lower else prev_results[-1]
            search_name = target_item.get('استاد راهنما' if 'استاد' in query_lower else 'نویسنده', '').strip()
            if search_name:
                previous_row_ids = [r['رديف'] for r in last_shown_results.get(chat_id, [])]
                search_results_raw = search_theses(search_name, k=None, distance_threshold=1.2, exclude_rows=previous_row_ids)
                search_results = filter_results_with_gpt(f"پایان‌نامه‌های {search_name}", search_results_raw)
                if search_results:
                    save_search_results(chat_id, search_results, search_name)
                    author_search_done = True
                    is_followup = False
                else:
                    return (f"متأسفم، پایان‌نامه دیگری از «{search_name}» پیدا نکردم.", False)

    if is_followup and not author_search_done:
        if not (prev_results := get_last_search_results(chat_id)):
            return ("متأسفم، نتایج قبلی پیدا نشد.", False)

        if any(kw in query_lower for kw in ['شرح', 'توضیح', 'درباره', 'جزئیات']):
            if not (shown_results := last_shown_results.get(chat_id, [])):
                return ("متأسفم، هنوز پایان‌نامه‌ای معرفی نکردم.", False)
            selected_item = shown_results[-1]
            title = selected_item.get('عنوان') or selected_item.get('عنوان پایان‌نامه', '')
            author = selected_item.get('نویسنده', 'نامشخص')
            try:
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"عنوان: «{title}»\nپژوهشگر: {author}\n\nسوال: {user_query}"}
                    ],
                    max_tokens=500,
                    temperature=0.7
                )
                return (response.choices[0].message.content, False)
            except:
                return ("متأسفم، نتوانستم توضیح دهم.", False)

        if any(word in query_lower for word in ['بیشتر', 'باز', 'دوباره']):
            previous_row_ids = [r['رديف'] for r in last_shown_results.get(chat_id, [])]
            last_query = get_last_query(chat_id)
            search_results_raw = search_theses(last_query, k=None, distance_threshold=1.0, exclude_rows=previous_row_ids)
            search_results = [r for r in filter_results_with_gpt(user_query, search_results_raw, last_query) if r['رديف'] not in previous_row_ids]
            if not search_results:
                return ("متأسفم، پایان‌نامه جدیدی پیدا نکردم.", False)
            save_search_results(chat_id, search_results, last_query)
            is_followup = False
        else:
            search_results = filter_results_with_gpt(user_query, prev_results) or prev_results[:5]

    elif not author_search_done:
        print(f"🔍 Search: {user_query}")
        search_results_raw = search_theses(user_query, k=None, distance_threshold=0.85)
        if len(search_results_raw) < 3:
            print(f"   ⚠️ Low results, threshold increased")
            search_results_raw = search_theses(user_query, k=None, distance_threshold=1.2)
        if not search_results_raw:
            return ("متأسفم، پایان‌نامه مرتبطی پیدا نکردم.", False)
        search_results = filter_results_with_gpt(user_query, search_results_raw, user_query) or search_results_raw[:6]
        search_results = search_results[:10]
        save_search_results(chat_id, search_results, user_query)
        last_shown_results[chat_id] = search_results[:6]

    context = "\n".join([
        f"«{r.get('عنوان') or r.get('عنوان پایان‌نامه', '')}» — پژوهشگر: {clean_text_for_display(r.get('نویسنده', ''))}, "
        f"استاد راهنما: {clean_text_for_display(r.get('استاد راهنما', ''))}, مقطع: {clean_text_for_display(format_field(r.get('مقطع')))}, "
        f"رشته: {clean_text_for_display(format_field(r.get('رشته')) or format_field(r.get('رشته تحصیلی')))}, "
        f"سال: {clean_text_for_display(format_field(r.get('سال')) or format_field(r.get('سال دفاع')))}"
        for r in search_results
    ])

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"پایان‌نامه‌ها:\n{context}\n\nسوال: {user_query}\n\n**فرمت خروجی:**\n📄 «عنوان»\n   پژوهشگر: ...\n   استاد راهنما: ...\n   مقطع: ...\n   رشته: ...\n   سال: ...\n\n**مهم:** اگر سال '...' بود، از 'نامشخص' استفاده کن."}
            ],
            max_tokens=1500,
            temperature=0.1
        )
        assistant_response = response.choices[0].message.content

        if mentioned_titles := re.findall(r'📄 «([^»]+)»', assistant_response):
            shown_items = []
            for title in mentioned_titles:
                for item in search_results:
                    if title.strip() == (item.get('عنوان') or item.get('عنوان پایان‌نامه', '')).strip():
                        shown_items.append(item)
                        break
            if shown_items:
                last_shown_results[chat_id] = shown_items

        add_to_conversation(chat_id, "user", user_query)
        add_to_conversation(chat_id, "assistant", assistant_response)

        return (assistant_response, not is_followup)
    except Exception as e:
        print(f"❌ Error: {e}")
        return ("متأسفم، مشکلی پیش آمد.", False)


# Telegram Commands
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["📄 جستجوی پایان‌نامه"], ["📖 راهنما", "🔄 مکالمه جدید"]]
    await update.message.reply_text(
        "سلام! 👋\n\n"
        "به ربات هوشمند پایان‌نامه‌های دانشگاه خوارزمی خوش آمدید! 📄\n\n"
        "من می‌توانم:\n"
        "✅ پایان‌نامه‌های مناسب را پیشنهاد دهم\n"
        "✅ بر اساس استاد راهنما، رشته، سال جستجو کنم\n"
        "✅ به سوالات پی‌درپی شما پاسخ دهم (تا 3 روز)\n"
        "✅ نتایج را فیلتر کنم\n\n"
        "💡 حافظه مکالمه: 3 روز\n\n"
        "برای شروع مکالمه جدید: /new",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )


async def new_conversation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    for d in [conversation_memory, search_results_memory, last_query_memory, last_shown_results]:
        d.pop(chat_id, None)
    reset_filter_state(chat_id)
    await update.message.reply_text(
        "✅ مکالمه جدید شروع شد!\n\nحالا می‌توانید سوال جدیدی بپرسید. 😊",
        reply_markup=ReplyKeyboardRemove()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 **راهنمای استفاده:**\n\n"
        "🔹 سوال خود را بپرسید\n"
        "🔹 سوالات بعدی را درباره همان نتایج بپرسید\n"
        "🔹 از فیلترها برای محدود کردن نتایج استفاده کنید\n"
        "🔹 برای مکالمه جدید: /new\n\n"
        "**مثال:**\n"
        "• پایان نامه یادگیری ماشین\n"
        "• استاد راهنمای اولی کیه؟\n"
        "• باز هم بده",
        parse_mode='Markdown'
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = update.effective_chat.id

    if user_message == "📄 جستجوی پایان‌نامه":
        await update.message.reply_text("لطفاً سوال خود را بپرسید")
        return
    elif user_message == "📖 راهنما":
        await help_command(update, context)
        return
    elif user_message == "🔄 مکالمه جدید":
        await new_conversation_command(update, context)
        return

    await update.message.chat.send_action(action="typing")

    # Filter management
    if filter_state[chat_id].get('active', False):
        if filter_result := handle_filter_interaction(user_message, chat_id):
            message, keyboard, should_show = filter_result

            if message is None and keyboard is None:
                pass  # Exit filter, continue searching
            elif keyboard and not isinstance(keyboard, ReplyKeyboardRemove):
                await update.message.reply_text(message, reply_markup=keyboard)
                return
            elif should_show:
                # ✅ Display success message
                await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())

                # ✅ Get filtered results
                filtered_results = get_last_search_results(chat_id)
                print(f"🔍 DEBUG: Number of filtered results: {len(filtered_results)}")

                if filtered_results:
                    result_texts = []
                    for r in filtered_results[:6]:
                        title = r.get('عنوان') or r.get('عنوان پایان‌نامه', '')
                        author = clean_text_for_display(r.get('نویسنده', ''))
                        advisor = clean_text_for_display(r.get('استاد راهنما', ''))
                        degree = clean_text_for_display(format_field(r.get('مقطع')))
                        field = clean_text_for_display(format_field(r.get('رشته')) or format_field(r.get('رشته تحصیلی')))
                        year = clean_text_for_display(format_field(r.get('سال')) or format_field(r.get('سال دفاع')))

                        result_text = (
                            f"📄 «{title}»\n"
                            f"   پژوهشگر: {author}\n"
                            f"   استاد راهنما: {advisor}\n"
                            f"   مقطع: {degree}\n"
                            f"   رشته: {field}\n"
                            f"   سال: {year}\n"
                        )
                        result_texts.append(result_text)
                        print(f"📄 DEBUG: was added: {title[:30]}...")

                    # ✅ Send Results
                    results_message = "\n".join(result_texts)
                    print(f"✉️ DEBUG: Sending {len(result_texts)} thesis...")
                    await update.message.reply_text(results_message)
                    print("✅ DEBUG: Results sent!")
                else:
                    print("❌ DEBUG: filtered_results is empty!")
                    await update.message.reply_text("متأسفم، نتایجی برای نمایش وجود ندارد.")
                return
            else:
                if message:
                    await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())
                return

    # Normal Search
    result = generate_rag_response(user_message, chat_id)
    response, is_new_search = result if isinstance(result, tuple) else (result, False)
    await update.message.reply_text(response)

    # Filter suggestion
    if should_offer_filter(chat_id, get_last_search_results(chat_id), is_new_search):
        await update.message.reply_text("💡 آیا مایلید نتایج را فیلتر کنید؟ (بله/خیر)")
        filter_state[chat_id].update({'active': True, 'stage': 'ask', 'last_offer': datetime.now()})


def main():
    print("="*60)
    print("🤖 Launching thesis bot")
    print("="*60)

    if not initialize_embedder():
        print("❌ Error in setup!")
        return

    TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("new", new_conversation_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Thesis bot is ready")
    print("="*60)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ Bot stopped")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
