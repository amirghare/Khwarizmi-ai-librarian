from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from collections import defaultdict
from datetime import datetime

MODE_IDLE = "idle"
MODE_BOOK = "book"
MODE_THESIS = "thesis"
MODE_REGULATIONS = "regulations"

user_mode = defaultdict(lambda: MODE_IDLE)

# Import book_bot
try:
    import book_bot
    BOOK_MODULE_AVAILABLE = True
    print("✅ book_bot module loaded")
except Exception as e:
    BOOK_MODULE_AVAILABLE = False
    print(f"⚠️ Error loading book_bot: {e}")

# Import thesis_bot
try:
    import thesis_bot
    THESIS_MODULE_AVAILABLE = True
    print("✅ thesis_bot module loaded")
except Exception as e:
    THESIS_MODULE_AVAILABLE = False
    print(f"⚠️ Error loading thesis_bot: {e}")

# Import regulations_bot
try:
    import regulations_bot
    REGULATIONS_MODULE_AVAILABLE = True
    print("✅ regulations_bot module loaded")
except Exception as e:
    REGULATIONS_MODULE_AVAILABLE = False
    print(f"⚠️ Error loading regulations_bot: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_mode[chat_id] = MODE_IDLE

    keyboard = [
        [InlineKeyboardButton("📚 جستجوی کتاب فارسی", callback_data="mode_book")],
        [InlineKeyboardButton("📄 جستجوی پایان‌نامه فارسی", callback_data="mode_thesis")],
        [InlineKeyboardButton("📋 قوانین و مقررات کتابخانه", callback_data="mode_regulations")],  # ✅ دکمه جدید
        [InlineKeyboardButton("ℹ️ درباره ما", callback_data="about")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_message = (
        "🎓 **سلام! به ربات هوشمند کتابخانه دانشگاه خوارزمی خوش آمدید!**\n\n"
        "لطفاً نوع سرویس مورد نظر خود را انتخاب کنید:\n\n"
        "📚 **جستجوی کتاب فارسی**\n"
        "   جستجو در میان هزاران کتاب فارسی\n\n"
        "📄 **جستجوی پایان‌نامه فارسی**\n"
        "   جستجو در پایان‌نامه‌های دانشگاه\n\n"
        "📋 **قوانین و مقررات کتابخانه**\n"
        "   پاسخ به سوالات درباره قوانین و آیین‌نامه‌ها\n\n"
        "ℹ️ **درباره ما**\n"
        "   اطلاعات بیشتر درباره ربات\n\n"
        "💡 برای بازگشت به این منو: /start"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            welcome_message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            welcome_message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id

    # Book mode
    if query.data == "mode_book":
        if not BOOK_MODULE_AVAILABLE:
            await query.edit_message_text(
                "❌ متأسفانه ماژول جستجوی کتاب در دسترس نیست.\n\n"
                "لطفاً با مدیر سیستم تماس بگیرید."
            )
            return

        user_mode[chat_id] = MODE_BOOK

        await query.edit_message_text(
            "📚 **حالت جستجوی کتاب فعال شد**\n\n"
            "حالا می‌توانید نام کتاب، نویسنده یا موضوع مورد نظرتان را بنویسید.\n\n"
            "**مثال‌ها:**\n"
            "• کتاب‌های نیما یوشیج\n"
            "• کتاب درباره یادگیری ماشین\n"
            "• شعرهای حافظ\n\n"
            "💡 **نکته:** می‌توانید سوالات پی‌درپی بپرسید، مثلاً:\n"
            "  - نویسنده کتاب دوم کیه؟\n"
            "  - باز هم کتاب بده\n"
            "  - کدوم بهتره؟\n\n"
            "🔙 برای بازگشت: /start\n"
            "🔄 برای مکالمه جدید: /new",
            parse_mode='Markdown'
        )

    # Thesis mode
    elif query.data == "mode_thesis":
        if not THESIS_MODULE_AVAILABLE:
            await query.edit_message_text(
                "❌ متأسفانه ماژول جستجوی پایان‌نامه در دسترس نیست.\n\n"
                "لطفاً با مدیر سیستم تماس بگیرید."
            )
            return

        user_mode[chat_id] = MODE_THESIS

        await query.edit_message_text(
            "📄 **حالت جستجوی پایان‌نامه فعال شد**\n\n"
            "حالا می‌توانید موضوع، استاد راهنما یا پژوهشگر مورد نظرتان را بنویسید.\n\n"
            "**مثال‌ها:**\n"
            "• پایان‌نامه درباره یادگیری ماشین\n"
            "• استاد راهنما دکتر احمدی\n"
            "• پایان‌نامه‌های رشته کامپیوتر\n\n"
            "💡 **نکته:** می‌توانید نتایج را فیلتر کنید بر اساس:\n"
            "  - سال دفاع\n"
            "  - مقطع تحصیلی\n"
            "  - استاد راهنما\n"
            "  - رشته تحصیلی\n\n"
            "🔙 برای بازگشت: /start\n"
            "🔄 برای مکالمه جدید: /new",
            parse_mode='Markdown'
        )

    # Regulations mode
    elif query.data == "mode_regulations":
        if not REGULATIONS_MODULE_AVAILABLE:
            await query.edit_message_text(
                "❌ متأسفانه ماژول قوانین و مقررات در دسترس نیست.\n\n"
                "لطفاً با مدیر سیستم تماس بگیرید."
            )
            return

        user_mode[chat_id] = MODE_REGULATIONS

        await query.edit_message_text(
            "📋 **حالت قوانین و مقررات فعال شد**\n\n"
            "حالا می‌توانید سوالات خود را درباره قوانین، آیین‌نامه‌ها و مقررات کتابخانه بپرسید.\n\n"
            "**مثال‌ها:**\n"
            "• چطور می‌تونم کتاب اهدا کنم؟\n"
            "• شرایط دسترسی به پایان‌نامه‌ها چیه؟\n"
            "• برای تحویل پایان‌نامه چی نیاز دارم؟\n"
            "• کتاب‌های قدیمی رو قبول می‌کنید؟\n\n"
            "💡 **نکته:** من فقط درباره قوانین موجود پاسخ می‌دهم.\n\n"
            "🔙 برای بازگشت: /start\n"
            "🔄 برای مکالمه جدید: /new",
            parse_mode='Markdown'
        )

    # About us
    elif query.data == "about":
        keyboard = [[InlineKeyboardButton("🔙 بازگشت به منو اصلی", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "ℹ️ **درباره ما**\n\n"
            "🎨 **کاری از تیم برنامه‌نویسی هسته فناوز DarkCube**\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✨ **امکانات:**\n"
            "• جستجوی هوشمند در هزاران کتاب و پایان‌نامه\n"
            "• پاسخ به سوالات درباره قوانین کتابخانه\n"
            "• پاسخ به سوالات پیچیده و متنی\n"
            "• فیلترهای پیشرفته\n"
            "• حافظه مکالمه تا 7 روز\n"
            "• پشتیبانی از سوالات follow-up\n\n"
            "📊 **آمار:**\n"
            "• بیش از 100,000 کتاب\n"
            "• بیش از 20,000 پایان‌نامه\n"
            "• دقت جستجوی بالای 90%\n\n",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    elif query.data == "back_to_menu":
        await start_command(update, context)


async def new_conversation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    mode = user_mode.get(chat_id, MODE_IDLE)

    if mode == MODE_IDLE:
        await update.message.reply_text(
            "✅ لطفاً ابتدا نوع سرویس را انتخاب کنید.\n\n"
            "برای انتخاب: /start"
        )
        return

    try:
        # Clear memory based on mode
        if mode == MODE_BOOK and BOOK_MODULE_AVAILABLE:
            book_bot.conversation_memory.pop(chat_id, None)
            book_bot.search_results_memory.pop(chat_id, None)
            book_bot.last_query_memory.pop(chat_id, None)
            book_bot.last_shown_results.pop(chat_id, None)
            mode_name = "**کتاب**"

        elif mode == MODE_THESIS and THESIS_MODULE_AVAILABLE:
            thesis_bot.conversation_memory.pop(chat_id, None)
            thesis_bot.search_results_memory.pop(chat_id, None)
            thesis_bot.last_query_memory.pop(chat_id, None)
            thesis_bot.last_shown_results.pop(chat_id, None)
            thesis_bot.filter_state.pop(chat_id, None)
            mode_name = "**پایان‌نامه**"

        elif mode == MODE_REGULATIONS and REGULATIONS_MODULE_AVAILABLE:
            regulations_bot.conversation_memory.pop(chat_id, None)
            mode_name = "**قوانین و مقررات**"

        else:
            mode_name = "**نامشخص**"

        await update.message.reply_text(
            f"✅ مکالمه جدید در حالت {mode_name} شروع شد!\n\n"
            "حالا می‌توانید سوال جدیدی بپرسید. 😊",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )

    except Exception as e:
        print(f"⚠️ Error clearing memory: {e}")
        await update.message.reply_text(
            "✅ مکالمه جدید شروع شد!\n\n"
            "حالا می‌توانید سوال جدیدی بپرسید. 😊",
            reply_markup=ReplyKeyboardRemove()
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    mode = user_mode.get(chat_id, MODE_IDLE)

    if mode == MODE_BOOK:
        help_text = (
            "📖 **راهنمای جستجوی کتاب:**\n\n"
            "🔹 نام کتاب، نویسنده یا موضوع را بنویسید\n"
            "🔹 سوالات بعدی را درباره همان نتایج بپرسید\n"
            "🔹 برای مکالمه جدید: /new\n\n"
            "**مثال مکالمه:**\n"
            "👤 کتاب‌های نیما یوشیج\n"
            "🤖 [6 کتاب پیشنهاد]\n\n"
            "👤 من مبتدیم، کدوم رو پیشنهاد میدی؟\n"
            "🤖 [توصیه بر اساس سطح]\n\n"
            "👤 نویسنده اولی کیه؟\n"
            "🤖 [نام نویسنده]\n\n"
            "👤 باز هم کتاب بده\n"
            "🤖 [6 کتاب جدید]"
        )

    elif mode == MODE_THESIS:
        help_text = (
            "📖 **راهنمای جستجوی پایان‌نامه:**\n\n"
            "🔹 موضوع، استاد راهنما یا پژوهشگر را بنویسید\n"
            "🔹 از فیلترها برای محدود کردن نتایج استفاده کنید\n"
            "🔹 برای مکالمه جدید: /new\n\n"
            "**مثال مکالمه:**\n"
            "👤 پایان‌نامه درباره یادگیری ماشین\n"
            "🤖 [6 پایان‌نامه پیشنهاد]\n\n"
            "👤 استاد راهنمای اولی کیه؟\n"
            "🤖 [نام استاد]\n\n"
            "👤 آیا مایلید نتایج را فیلتر کنید؟\n"
            "🤖 [منوی فیلترها]"
        )

    elif mode == MODE_REGULATIONS:
        help_text = (
            "📖 **راهنمای قوانین و مقررات:**\n\n"
            "🔹 سوال خود را درباره قوانین بپرسید\n"
            "🔹 برای مکالمه جدید: /new\n\n"
            "**مثال‌های سوال:**\n"
            "• چطور می‌تونم کتاب اهدا کنم؟\n"
            "• شرایط دسترسی به پایان‌نامه‌ها چیه؟\n"
            "• فرم اهدا کتاب کجاست؟\n"
            "• کتاب‌های قدیمی رو قبول می‌کنید؟"
        )

    else:
        help_text = (
            "📖 **راهنمای استفاده:**\n\n"
            "لطفاً ابتدا نوع سرویس را انتخاب کنید:\n\n"
            "/start - منوی اصلی\n\n"
            "بعد از انتخاب حالت، می‌توانید:\n"
            "• سوالات خود را بپرسید\n"
            "• از دستورات زیر استفاده کنید:\n"
            "  /new - شروع مکالمه جدید\n"
            "  /help - نمایش راهنما\n"
            "  /start - بازگشت به منو اصلی"
        )

    await update.message.reply_text(help_text, parse_mode='Markdown')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = update.effective_chat.id
    mode = user_mode.get(chat_id, MODE_IDLE)

    if mode == MODE_IDLE:
        await update.message.reply_text(
            "لطفاً ابتدا نوع سرویس را از منو انتخاب کنید:\n\n"
            "/start - منوی اصلی"
        )
        return

    await update.message.chat.send_action(action="typing")

    try:
        # Book mode
        if mode == MODE_BOOK and BOOK_MODULE_AVAILABLE:
            response = book_bot.generate_rag_response(user_message, chat_id)
            await update.message.reply_text(response)

        # Thesis mode
        elif mode == MODE_THESIS and THESIS_MODULE_AVAILABLE:
            # Check filter status
            if thesis_bot.filter_state[chat_id].get('active', False):
                filter_result = thesis_bot.handle_filter_interaction(user_message, chat_id)

                if filter_result:
                    message, keyboard, should_show = filter_result

                    if message is not None:
                        if keyboard and not isinstance(keyboard, thesis_bot.ReplyKeyboardRemove):
                            await update.message.reply_text(message, reply_markup=keyboard)
                        else:
                            await update.message.reply_text(message, reply_markup=keyboard or thesis_bot.ReplyKeyboardRemove())

                        if should_show:
                            filtered_results = thesis_bot.get_last_search_results(chat_id)
                            if filtered_results:
                                for r in filtered_results[:6]:
                                    title = r.get('عنوان') or r.get('عنوان پایان‌نامه', '')
                                    author = thesis_bot.clean_text_for_display(r.get('نویسنده', ''))
                                    advisor = thesis_bot.clean_text_for_display(r.get('استاد راهنما', ''))
                                    degree = thesis_bot.clean_text_for_display(thesis_bot.format_field(r.get('مقطع')))
                                    field = thesis_bot.clean_text_for_display(
                                        thesis_bot.format_field(r.get('رشته')) or
                                        thesis_bot.format_field(r.get('رشته تحصیلی'))
                                    )
                                    year = thesis_bot.clean_text_for_display(
                                        thesis_bot.format_field(r.get('سال')) or
                                        thesis_bot.format_field(r.get('سال دفاع'))
                                    )

                                    result_text = (
                                        f"📄 «{title}»\n"
                                        f"   پژوهشگر: {author}\n"
                                        f"   استاد راهنما: {advisor}\n"
                                        f"   مقطع: {degree}\n"
                                        f"   رشته: {field}\n"
                                        f"   سال: {year}\n"
                                    )
                                    await update.message.reply_text(result_text)
                        return

            # Normal search
            result = thesis_bot.generate_rag_response(user_message, chat_id)
            response, is_new_search = result if isinstance(result, tuple) else (result, False)
            await update.message.reply_text(response)

            # Suggest filter
            if thesis_bot.should_offer_filter(
                chat_id,
                thesis_bot.get_last_search_results(chat_id),
                is_new_search
            ):
                await update.message.reply_text("💡 آیا مایلید نتایج را فیلتر کنید؟ (بله/خیر)")
                thesis_bot.filter_state[chat_id].update({
                    'active': True,
                    'stage': 'ask',
                    'last_offer': thesis_bot.datetime.now()
                })

        # Regulations mode
        elif mode == MODE_REGULATIONS and REGULATIONS_MODULE_AVAILABLE:
            response = regulations_bot.generate_response(user_message, chat_id)
            await update.message.reply_text(response)

        else:
            await update.message.reply_text(
                "متأسفم، این سرویس در دسترس نیست.\n\n"
                "برای انتخاب سرویس جدید: /start"
            )

    except Exception as e:
        print(f"❌ Error processing message: {e}")
        import traceback
        traceback.print_exc()

        await update.message.reply_text(
            "متأسفم، مشکلی پیش آمد. لطفاً دوباره تلاش کنید.\n\n"
            "اگر مشکل ادامه داشت:\n"
            "• /new - شروع مکالمه جدید\n"
            "• /start - بازگشت به منو اصلی"
        )


# Main
def main():
    print("="*60)
    print("🤖 Launching the combined library bot")
    print("="*60)

    # Check module availability
    if not BOOK_MODULE_AVAILABLE:
        print("⚠️ book_bot module is not available")
    if not THESIS_MODULE_AVAILABLE:
        print("⚠️ thesis_bot module is not available")
    if not REGULATIONS_MODULE_AVAILABLE:
        print("⚠️ regulations_bot module is not available")

    if not BOOK_MODULE_AVAILABLE and not THESIS_MODULE_AVAILABLE and not REGULATIONS_MODULE_AVAILABLE:
        print("❌ No modules are available!")
        return

    # Load embedders
    if BOOK_MODULE_AVAILABLE:
        print("🔄 Loading book_bot...")
        if not book_bot.initialize_embedder():
            print("❌ Error loading book_bot")
            return
        print("✅ book_bot is ready")

    if THESIS_MODULE_AVAILABLE:
        print("🔄 Loading thesis_bot...")
        if not thesis_bot.initialize_embedder():
            print("❌ Error loading thesis_bot")
            return
        print("✅ thesis_bot is ready")

    if REGULATIONS_MODULE_AVAILABLE:
        print("🔄 Loading regulations_bot...")
        if not regulations_bot.initialize_handler():
            print("❌ Error loading regulations_bot")
            return
        print("✅ regulations_bot is ready")

    TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("new", new_conversation_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("=" * 60)
    print("✅ Combined bot is ready!")
    if BOOK_MODULE_AVAILABLE:
        print("📚 Book mode: active")
    if THESIS_MODULE_AVAILABLE:
        print("📄 Thesis mode: active")
    if REGULATIONS_MODULE_AVAILABLE:
        print("📋 Regulations mode: active")
    print("=" * 60)

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
