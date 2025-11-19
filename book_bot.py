
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
import config
from book_embedder import BookEmbedder
from book_details import BookDetailsLoader
from collections import defaultdict
from datetime import datetime, timedelta
import re


last_shown_results = defaultdict(list)  # ✅ Separate for tracking display
openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
embedder = None
book_details_loader = None
conversation_memory = defaultdict(list)
search_results_memory = defaultdict(list)
last_message_time = defaultdict(lambda: datetime.now())
last_query_memory = defaultdict(str)

ORIGINAL_EXCEL_PATH = "output/final_normalize.xlsx"

config.SYSTEM_PROMPT = """
شما یک دستیار هوشمند کتابخانه دانشگاه خوارزمی هستید.
**قوانین مهم:**
1. **فقط از کتاب‌های ارائه شده استفاده کنید**
2. **نحوه پاسخ:**
   a) جستجوی اولیه: تمام کتاب‌ها را معرفی کنید
   b) درخواست بیشتر: فقط کتاب‌های جدید
   c) سوال مقایسه‌ای: مقایسه کنید
   d) سوال توضیحی: توضیح دهید
3. **فرمت:**
   🔹 «عنوان»
   نویسنده: ...
   ناشر: ...
   (و بقیه)
4. **زبان**: فارسی، دوستانه، مختصر
5. **ممنوعیت‌ها:**
   - "کتابی نداریم" نگو
   - کتاب تکراری معرفی نکن
"""

def format_cutter(cutter_raw):
    if not cutter_raw or str(cutter_raw).lower() in ['nan', 'none', '']:
        return "نامشخص"
    cutter = str(cutter_raw).strip()
    if cutter.endswith('/'):
        cutter = cutter[:-1]
    return cutter

def format_location(location_raw):
    if not location_raw or str(location_raw).lower() in ['nan', 'none', '']:
        return "کتابخانه مرکزی دانشگاه خوارزمی"
    return str(location_raw).strip()

def enrich_search_result(result):
    if book_details_loader is None:
        return result
    row_id = result.get('رديف')
    if not row_id:
        return result
    details = book_details_loader.get_book_details(row_id)
    if details:
        enriched = result.copy()
        enriched.update(details)
        return enriched
    return result


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
    if expired_chats:
        print(f"🗑️ Cleaned: {len(expired_chats)} old conversations")


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


def get_conversation_history(chat_id, limit=20):
    if chat_id not in conversation_memory:
        return []
    current_time = datetime.now()
    three_days_ago = current_time - timedelta(days=3)
    recent_messages = [
        msg for msg in conversation_memory[chat_id]
        if msg["timestamp"] > three_days_ago
    ]
    return recent_messages[-limit:]


def save_search_results(chat_id, results, query=""):
    search_results_memory[chat_id] = results
    if query:
        last_query_memory[chat_id] = query
    last_message_time[chat_id] = datetime.now()


def get_last_search_results(chat_id):
    return search_results_memory.get(chat_id, [])


def get_last_query(chat_id):
    return last_query_memory.get(chat_id, "")


def format_book_output(gpt_response, search_results):
    mentioned_titles = re.findall(r'[«"]([^»"]+)[»"]', gpt_response)

    if not mentioned_titles:
        mentioned_titles = [book.get('عنوان', '') for book in search_results[:5]]

    def normalize_title(title):
        return re.sub(r'\s+', ' ', title.strip())

    mentioned_titles_norm = [normalize_title(t) for t in mentioned_titles]

    formatted_books = []
    used_indices = set()

    for title_norm in mentioned_titles_norm:
        for idx, book in enumerate(search_results):
            if idx in used_indices:
                continue

            book_title_norm = normalize_title(book.get('عنوان', ''))

            if title_norm in book_title_norm or book_title_norm in title_norm or title_norm == book_title_norm:
                book_formatted = f"""🔹 «{book['عنوان']}»
   نویسنده: {book.get('پديدآورنده', 'نامشخص')}
   ناشر: {book.get('ناشر', 'نامشخص')}
   سال انتشار: {book.get('تاريخ نشر', 'نامشخص')}
   شماره بازیابی: {book.get('شماره_بازیابی', 'نامشخص')}
   محل نگهداری: {book.get('محل_نگهداری', 'کتابخانه مرکزی')}
   موضوع: {book.get('موضوع', 'نامشخص')}"""

                formatted_books.append(book_formatted)
                used_indices.add(idx)
                break

    if not formatted_books:
        for book in search_results[:5]:
            book_formatted = f"""🔹 «{book['عنوان']}»
   نویسنده: {book.get('پديدآورنده', 'نامشخص')}
   ناشر: {book.get('ناشر', 'نامشخص')}
   سال انتشار: {book.get('تاريخ نشر', 'نامشخص')}
   شماره بازیابی: {book.get('شماره_بازیابی', 'نامشخص')}
   محل نگهداری: {book.get('محل_نگهداری', 'کتابخانه مرکزی')}
   موضوع: {book.get('موضوع', 'نامشخص')}"""
            formatted_books.append(book_formatted)

    gpt_text_lines = []
    for line in gpt_response.split('\n'):
        line = line.strip()
        if line.startswith('«') or line.startswith('نویسنده:') or line.startswith('ناشر:') or line.startswith('سال:') or line.startswith('موضوع:'):
            continue
        if line and len(line) > 3:
            gpt_text_lines.append(line)

    gpt_text_only = '\n'.join(gpt_text_lines)

    final_output = ""
    if gpt_text_only and len(gpt_text_only) > 20:
        final_output += gpt_text_only.strip() + "\n\n"

    final_output += "\n\n".join(formatted_books)

    return final_output


# RAG helper functions
def initialize_embedder():
    global embedder, book_details_loader
    print("🔄 Loading FAISS index...")
    try:
        embedder = BookEmbedder(api_key=config.OPENAI_API_KEY)
        embedder.load_index(config.FAISS_INDEX_PATH)
        print("✅ FAISS index loaded")
    except Exception as e:
        print(f"❌ Error loading index: {e}")
        return False
    print("🔄 Loading book details...")
    try:
        book_details_loader = BookDetailsLoader(ORIGINAL_EXCEL_PATH)
        print("✅ Book details loaded")
    except Exception as e:
        print(f"❌ Error loading details: {e}")
        return False
    return True


def is_followup_question(query, chat_id):
    followup_keywords = [
        'بله', 'آره', 'اوکی', 'باشه', 'بیشتر', 'جدیدتر', 'قدیمی‌تر',
        'مبتدی', 'پیشرفته', 'ساده', 'سخت', 'بهترین', 'کدوم', 'کدام',
        'اولی', 'دومی', 'اون', 'این', 'همون', 'همین', 'باز', 'دوباره',
        'چند تا دیگه', 'چندتا دیگه', 'تا دیگه', 'معرفی کن', 'نشون بده',
        'بگو', 'توضیح بده', 'چطوره', 'راجع', 'درباره اون', 'درباره این',
        'دوست دارم', 'دوس دارم', 'عالی بود', 'بهترین', 'ازش', 'از اون',
        'بیشتر از', 'جزئیات', 'خلاصه', 'توضیح', 'چرا', 'چطور', 'مثال',
        'شبیه', 'مشابه', 'کتاب دوم', 'کتاب آخر', 'شرح بده', 'درباره کتاب',
        'بیشتر شرح', 'نویسنده آخر', 'نویسنده کتاب آخر', 'این نویسنده کیه'
    ]
    query_lower = query.lower()
    has_followup_keyword = any(keyword in query_lower for keyword in followup_keywords)
    has_previous_results = len(get_last_search_results(chat_id)) > 0
    if has_followup_keyword and has_previous_results and len(query.split()) <= 10:
        return True
    new_search_indicators = ['کتاب', 'نویسنده', 'شعر', 'داستان', 'رمان']
    if any(indicator in query_lower for indicator in new_search_indicators):
        if has_followup_keyword and ('دیگه' in query_lower or 'دیگر' in query_lower or 'باز' in query_lower):
            return True
        else:
            return False
    return has_followup_keyword and has_previous_results


def filter_results_with_gpt(user_query, search_results, original_query=""):
    if not search_results:
        return []
    books_list = []
    for i, r in enumerate(search_results, 1):
        books_list.append(f"{i}. «{r['عنوان']}» - نویسنده: {r['پديدآورنده']}, موضوع: {r['موضوع']}")
    books_text = "\n".join(books_list)
    filter_prompt = f"""
سوال: "{user_query}"
موضوع اصلی: "{original_query}"

لیست کتاب‌ها:
{books_text}

فقط مرتبط‌ها را انتخاب کن.
خروجی: شماره‌ها با کاما (مثل '1,3') یا 'هیچکدام'.
"""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": filter_prompt}],
            max_tokens=100,
            temperature=0.1
        )
        answer = response.choices[0].message.content.strip()
        if "هیچکدام" in answer.lower():
            return []
        numbers = re.findall(r'\b\d+\b', answer)
        numbers = [int(n) for n in numbers if 1 <= int(n) <= len(search_results)]
        filtered = [search_results[n-1] for n in set(numbers)]
        print(f"🔍 GPT Filter: {len(filtered)}/{len(search_results)} مرتبط")
        if len(filtered) < 2 and len(search_results) >= 2:
            return search_results[:5]
        return filtered
    except Exception as e:
        print(f"⚠️ Error in filter: {e}")
        return search_results[:5]


def search_books(query, k=None, distance_threshold=0.8, exclude_rows=None):
    if embedder is None:
        return []
    try:
        results = embedder.search(query, k=k or 30)
        enriched_results = []
        for r in results:
            enriched = enrich_search_result(r)
            if enriched['distance'] < distance_threshold:
                if exclude_rows is None or enriched['رديف'] not in exclude_rows:
                    enriched_results.append(enriched)
        print(f"📊 Search: '{query[:50]}...' → Result: {len(enriched_results)} ")
        return enriched_results[:k] if k else enriched_results[:10]
    except Exception as e:
        print(f"❌ Error in search: {e}")
        return []


def generate_rag_response(user_query, chat_id):
    clean_old_conversations()

    # Greeting
    greetings = ['سلام', 'درود', 'صبح بخیر', 'عصر بخیر', 'شب بخیر', 'خوبی', 'چطوری', 'حالت', 'hello', 'hi']
    if any(greet in user_query.lower() for greet in greetings) and len(user_query.split()) <= 3:
        return "سلام! 👋\n\nچطور می‌تونم کمکتون کنم؟\nمثال: کتاب‌های نیما یوشیج"

    is_followup = is_followup_question(user_query, chat_id)
    query_lower = user_query.lower()

    # ✅ FIX 2: Detect author
    asking_author_patterns = [
        r'نویسنده\s+(کتاب\s+)?(اول|دوم|سوم|چهارم|پنجم|آخر|اخر|۱|۲|۳|۴|۵|1|2|3|4|5)ی?\s*(کیه|چیه|است|هست)?',
        r'(اول|دوم|سوم|چهارم|پنجم|آخر|اخر|۱|۲|۳|۴|۵|1|2|3|4|5)ی?\s+نویسنده\s*اش?\s*(کیه|چیه)?',
    ]

    only_asking_author_name = (
        any(re.search(pattern, query_lower) for pattern in asking_author_patterns) and
        'معرفی' not in query_lower and
        'بیشتر' not in query_lower and
        'دیگه' not in query_lower and
        'دیگر' not in query_lower
    )

    if only_asking_author_name:
        print("\n" + "="*60)
        print("📝 Author's question")

        shown_results = last_shown_results.get(chat_id, [])

        print(f"📋 Counts: {len(shown_results)}")
        for i, book in enumerate(shown_results, 1):
            print(f"   {i}. «{book['عنوان'][:40]}...»")

        if not shown_results:
            print("="*60 + "\n")
            return "متأسفم، هنوز کتابی معرفی نکردم."

        # ✅ FIX 2: Correct diagnosis index
        position = -1
        if 'اول' in query_lower or '۱' in query_lower or '1' in query_lower:
            position = 0
        elif 'دوم' in query_lower or '۲' in query_lower or '2' in query_lower:
            position = 1
        elif 'سوم' in query_lower or '۳' in query_lower or '3' in query_lower:
            position = 2
        elif 'چهارم' in query_lower or '۴' in query_lower or '4' in query_lower:
            position = 3
        elif 'پنجم' in query_lower or '۵' in query_lower or '5' in query_lower:
            position = 4

        print(f"🎯 Index: {position}")

        if position >= 0 and position >= len(shown_results):
            print("="*60 + "\n")
            return f"متأسفم، من فقط {len(shown_results)} کتاب معرفی کردم."

        target_book = shown_results[position]
        title = target_book['عنوان']
        print(f"📖 Books: «{title[:50]}...»")

        author = target_book.get('پديدآورنده', '').strip()
        author = re.sub(r'(مولف|نوشته|تالیف|از|توسط)\s*', '', author, flags=re.IGNORECASE)
        author = re.sub(r'[/\.؛]', '', author)
        author = re.sub(r'\s+', ' ', author).strip()

        print(f"👤 Author: {author}")
        print("="*60 + "\n")

        if not author or author.lower() in ['nan', 'none', '']:
            return f"متأسفم، نویسنده کتاب «{title}» در سیستم ثبت نشده است."

        return f"نویسنده کتاب «{title}»، «{author}» است."


    # Search for books by author
    author_search_keywords = [
        'از این نویسنده', 'از نویسنده', 'نویسنده این', 'کتاب های این نویسنده',
        'کتاب دیگه از', 'کتاب اون نویسنده', 'نویسنده کتاب اول', 'نویسنده کتاب دوم',
        'کتاب همون نویسنده', 'ازش کتاب', 'از اون نویسنده', 'نویسنده کتاب آخر',
        'از نویسنده آخر', 'از نویسنده دوم', 'دوست دارم از نویسنده', 'دوس دارم از نویسنده',
        'از نویسنده کتاب دوم', 'از نویسنده کتاب آخر', 'چندتا کتاب از نویسنده',
        'کتاب دیگه ای داریم', 'این نویسنده کیه'
    ]

    author_search_done = False

    if is_followup and any(kw in query_lower for kw in author_search_keywords):
        print("📚 Author search request")

        prev_results = last_shown_results.get(chat_id, get_last_search_results(chat_id))

        if prev_results and len(prev_results) > 0:
            print(f"   📋 Count: {len(prev_results)}")

            # book selection
            if 'اول' in query_lower or '1' in query_lower or '۱' in query_lower:
                target_book = prev_results[0]
            elif 'دوم' in query_lower or '2' in query_lower or '۲' in query_lower:
                target_book = prev_results[1] if len(prev_results) > 1 else prev_results[0]
            elif 'سوم' in query_lower or '3' in query_lower or '۳' in query_lower:
                target_book = prev_results[2] if len(prev_results) > 2 else prev_results[0]
            elif 'آخر' in query_lower or 'اخر' in query_lower or 'آخرین' in query_lower:
                target_book = prev_results[-1]
            else:
                target_book = prev_results[-1]

            print(f"   📖 Book: {target_book['عنوان'][:40]}...")

            author_name = target_book.get('پديدآورنده', '').strip()
            author_name = re.sub(r'(مولف|نوشته|تالیف|از|توسط)\s*', '', author_name, flags=re.IGNORECASE)
            author_name = re.sub(r'[^\w\s,،]', ' ', author_name)
            author_name = re.sub(r'\s+', ' ', author_name).strip()

            if author_name.lower() in ['nan', 'none', ''] or not author_name:
                return "متأسفم، نام نویسنده معتبر نیست."

            print(f"   👤 Author: {author_name}")

            shown_results = last_shown_results.get(chat_id, [])
            previous_row_ids = [r['رديف'] for r in shown_results]

            search_results_raw = search_books(
                f"نویسنده دقیق: {author_name}",
                k=None,
                distance_threshold=1.2,
                exclude_rows=previous_row_ids
            )

            search_results = filter_results_with_gpt(
                f"کتاب‌های {author_name}",
                search_results_raw,
                original_query=f"کتاب‌های {author_name}"
            )

            if search_results and len(search_results) > 0:
                print(f"   ✅ {len(search_results)} کتاب از «{author_name}»")
                save_search_results(chat_id, search_results, author_name)
                author_search_done = True
                is_followup = False
            else:
                return f"متأسفم، کتاب دیگری از «{author_name}» پیدا نکردم. 😔"
        else:
            return "متأسفم، نتایج قبلی پیدا نشد."

    if is_followup:
        print(f"💬 Follow-up detected")
        prev_results = get_last_search_results(chat_id)
        last_query = get_last_query(chat_id)

        if not prev_results:
            return "متأسفم، نتایج قبلی پیدا نشد."

        explain_keywords = ['شرح', 'توضیح', 'درباره', 'جزئیات', 'خلاصه', 'بیشتر بگو', 'معرفی کن']
        is_explain_question = any(kw in query_lower for kw in explain_keywords)

        if is_explain_question:
            print("📖 Explanation question identified")

            shown_results = last_shown_results.get(chat_id, [])

            if not shown_results:
                return "متأسفم، هنوز کتابی معرفی نکردم."

            selected_book = None
            if 'اول' in query_lower or '۱' in query_lower or '1' in query_lower:
                selected_book = shown_results[0] if len(shown_results) > 0 else None
            elif 'دوم' in query_lower or '۲' in query_lower or '2' in query_lower:
                selected_book = shown_results[1] if len(shown_results) > 1 else None
            elif 'سوم' in query_lower or '۳' in query_lower or '3' in query_lower:
                selected_book = shown_results[2] if len(shown_results) > 2 else None
            elif 'آخر' in query_lower or 'اخر' in query_lower or 'این' in query_lower:
                selected_book = shown_results[-1]
            else:
                selected_book = shown_results[-1]

            if selected_book:
                title = selected_book['عنوان']
                author = selected_book.get('پديدآورنده', 'نامشخص')
                publisher = selected_book.get('ناشر', 'نامشخص')
                year = selected_book.get('تاريخ نشر', 'نامشخص')
                subject = selected_book.get('موضوع', '')

                print(f"   📖 کتاب: «{title[:40]}...»")

                single_context = (
                    f"عنوان: «{title}»\n"
                    f"نویسنده: {author}\n"
                    f"ناشر: {publisher}\n"
                    f"سال: {year}\n"
                    f"موضوع: {subject}"
                )

                history = get_conversation_history(chat_id, limit=5)
                messages = [{"role": "system", "content": config.SYSTEM_PROMPT}]
                for h in history:
                    messages.append({"role": h["role"], "content": h["content"][:300]})

                user_message = (
                    f"کتاب:\n{single_context}\n\n"
                    f"سوال: {user_query}\n\n"
                    f"**دستور:** فقط درباره این کتاب توضیح بده. "
                    f"یک پاراگراف کوتاه و مفید بنویس که این کتاب چیه و برای چه کسانی مناسبه."
                )
                messages.append({"role": "user", "content": user_message})

                try:
                    response = openai_client.chat.completions.create(
                        model=config.GPT_MODEL,
                        messages=messages,
                        max_tokens=500,
                        temperature=0.7
                    )
                    explanation = response.choices[0].message.content

                    add_to_conversation(chat_id, "user", user_query)
                    add_to_conversation(chat_id, "assistant", explanation)
                    return explanation

                except Exception as e:
                    print(f"❌ Error in explanation: {e}")
                    return f"متأسفم، نتوانستم درباره «{title}» توضیح دهم."

        if any(word in query_lower for word in ['بیشتر', 'باز', 'دوباره', 'چند تا دیگه', 'چندتا دیگه']):
            # ✅ FIX 1: exclude from last_shown_results (not search_results_memory)
            shown_results = last_shown_results.get(chat_id, [])
            previous_row_ids = [r['رديف'] for r in shown_results]

            print(f"📝 Count exclude: {len(previous_row_ids)}")
            print(f"🚫 IDs: {previous_row_ids[:5]}...")

            effective_query = last_query if last_query else query_lower
            effective_query = re.sub(r'\b(باز|بیشتر|دوباره|چند تا دیگه|چندتا دیگه)\b', '', effective_query, flags=re.IGNORECASE).strip()

            if not effective_query:
                effective_query = last_query if last_query else "کتاب‌های مرتبط"

            search_results_raw = search_books(
                effective_query,
                k=None,
                distance_threshold=1.0,
                exclude_rows=previous_row_ids  # ✅ exclude
            )

            search_results = filter_results_with_gpt(user_query, search_results_raw, last_query)

            # ✅ double-check for exclude
            search_results = [r for r in search_results if r['رديف'] not in previous_row_ids]

            if not search_results:
                return f"متأسفم، کتاب جدیدی پیدا نکردم. 😔\n\n✅ قبلاً {len(shown_results)} کتاب معرفی کردم."

            save_search_results(chat_id, search_results, last_query)
            is_followup = False
        else:
            search_results = filter_results_with_gpt(user_query, prev_results, last_query)
            if not search_results:
                search_results = prev_results[:5]

    elif not author_search_done:
        # New search
        print(f"🔍 Search: {user_query}")

        search_results_raw = search_books(user_query, k=None, distance_threshold=0.8)

        if not search_results_raw:
            search_results_raw = search_books(user_query, k=None, distance_threshold=1.4)

        if not search_results_raw:
            return "متأسفم، کتاب مرتبطی پیدا نکردم. 😔"

        search_results = filter_results_with_gpt(user_query, search_results_raw, user_query)

        if not search_results:
            search_results = search_results_raw[:6]

        search_results = search_results[:10]
        save_search_results(chat_id, search_results, user_query)

        last_shown_results[chat_id] = search_results[:6]

        print(f"💾 Save {len(search_results[:6])} Book:")
        for i, book in enumerate(search_results[:6], 1):
            print(f"   {i}. «{book['عنوان'][:40]}...»")

    # Create context and send to GPT (no changes)

    # Create context for GPT
    context_parts = []
    for r in search_results:
        context_parts.append(f"«{r['عنوان']}» — {r['پديدآورنده']}, {r['ناشر']}")
    context = "\n".join(context_parts)

    history = get_conversation_history(chat_id, limit=10)
    messages = [{"role": "system", "content": config.SYSTEM_PROMPT}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"][:500]})

    user_message = f"کتاب‌ها:\n{context}\n\nسوال: {user_query}"
    messages.append({"role": "user", "content": user_message})

    try:
        response = openai_client.chat.completions.create(
            model=config.GPT_MODEL,
            messages=messages,
            max_tokens=1500,
            temperature=0.1
        )
        assistant_response_raw = response.choices[0].message.content

        assistant_response = format_book_output(assistant_response_raw, search_results)

        mentioned_titles = re.findall(r'🔹 «([^»]+)»', assistant_response)

        if mentioned_titles:
            def normalize_title(title):
                return re.sub(r'\s+', ' ', title.replace('\u200c', ' ').strip())

            shown_books = []
            used_indices = set()

            for title in mentioned_titles:
                title_norm = normalize_title(title)
                for idx, book in enumerate(search_results):
                    if idx in used_indices:
                        continue
                    book_title_norm = normalize_title(book.get('عنوان', ''))
                    if book_title_norm == title_norm:
                        shown_books.append(book)
                        used_indices.add(idx)
                        break

            if shown_books:
                last_shown_results[chat_id] = shown_books

                print(f"\n💾 Update shown: {len(shown_books)} Book")
                for i, book in enumerate(shown_books, 1):
                    print(f"   {i}. «{book['عنوان'][:40]}...»")

        add_to_conversation(chat_id, "user", user_query)
        add_to_conversation(chat_id, "assistant", assistant_response)
        return assistant_response

    except Exception as e:
        print(f"❌ Error: {e}")
        return "متأسفم، مشکلی پیش آمد."


# Telegram commands
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["📚 جستجوی کتاب"], ["📖 راهنما", "🔄 مکالمه جدید"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    welcome_message = (
        "سلام! 👋\n\n"
        "به ربات هوشمند کتابخانه دانشگاه خوارزمی خوش آمدید! 📚\n\n"
        "من می‌توانم:\n"
        "✅ کتاب‌های مناسب را پیشنهاد دهم\n"
        "✅ به سوالات پی‌درپی شما پاسخ دهم (تا 3 روز)\n"
        "✅ کتاب‌ها را مقایسه کنم\n\n"
        "مثال مکالمه:\n"
        "شما: کتاب‌های نیما یوشیج\n"
        "من: [4 کتاب پیشنهاد]\n"
        "شما: من مبتدیم، بهترینش کدومه؟\n"
        "من: [پاسخ براساس همون نتایج]\n\n"
        "💡 حافظه مکالمه: 3 روز\n"
        "🗑️ پاک‌سازی خودکار: بعد از 1 هفته\n\n"
        "برای شروع مکالمه جدید: /new"
    )
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)


async def new_conversation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conversation_memory.pop(chat_id, None)
    search_results_memory.pop(chat_id, None)
    last_query_memory.pop(chat_id, None)
    last_shown_results.pop(chat_id, None)
    await update.message.reply_text(
        "✅ مکالمه جدید شروع شد!\n\n"
        "حالا می‌توانید سوال جدیدی بپرسید. 😊"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_message = (
        "📖 **راهنمای استفاده:**\n\n"
        "🔹 سوال خود را بپرسید\n"
        "🔹 سوالات بعدی را درباره همان نتایج بپرسید\n"
        "🔹 برای مکالمه جدید: /new\n\n"
        "**مثال:**\n"
        "• کتاب‌های نیما یوشیج\n"
        "• من مبتدیم، کدوم رو پیشنهاد میدی؟\n"
        "• کدوم جدیدتره؟\n"
        "• بیشتر بگو درباره اولی"
    )
    await update.message.reply_text(help_message, parse_mode='Markdown')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = update.effective_chat.id

    if user_message == "📚 جستجوی کتاب":
        await update.message.reply_text("لطفاً سوال خود را بپرسید")
        return
    elif user_message == "📖 راهنما":
        await help_command(update, context)
        return
    elif user_message == "🔄 مکالمه جدید":
        await new_conversation_command(update, context)
        return

    await update.message.chat.send_action(action="typing")
    response = generate_rag_response(user_message, chat_id)
    await update.message.reply_text(response)


def main():
    print("="*60)
    print("🤖 Launching the bot")
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

    print("✅ Bot is ready!")
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
