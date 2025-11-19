from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
import config
from regulations_loader import RegulationsLoader
from modules.regulations_handler import RegulationsHandler
from collections import defaultdict
from datetime import datetime, timedelta

openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
regulations_handler = None
conversation_memory = defaultdict(list)
last_message_time = defaultdict(lambda: datetime.now())


def initialize_handler():
    """Load regulations"""
    global regulations_handler

    print("🔄 Loading regulations...")

    try:
        # Load regulations text
        loader = RegulationsLoader("data/regulations")
        regulations_text = loader.get_regulations_text()

        if not regulations_text:
            print("❌ Regulations text is empty!")
            return False

        # Create handler
        regulations_handler = RegulationsHandler(regulations_text)

        print("✅ Regulations loaded successfully")
        return True

    except Exception as e:
        print(f"❌ Error loading regulations: {e}")
        return False


def clean_old_conversations():
    """Clean up old conversations"""
    current_time = datetime.now()
    expired_chats = []

    for chat_id, last_time in last_message_time.items():
        if current_time - last_time > timedelta(days=7):
            expired_chats.append(chat_id)

    for chat_id in expired_chats:
        conversation_memory.pop(chat_id, None)
        last_message_time.pop(chat_id, None)


def add_to_conversation(chat_id, role, content):
    """Add message to memory"""
    conversation_memory[chat_id].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now()
    })

    # Keep last 20 messages
    if len(conversation_memory[chat_id]) > 20:
        conversation_memory[chat_id] = conversation_memory[chat_id][-20:]

    last_message_time[chat_id] = datetime.now()


def get_conversation_history(chat_id, limit=10):
    """Get conversation history"""
    if chat_id not in conversation_memory:
        return []

    return conversation_memory[chat_id][-limit:]


def generate_response(user_query, chat_id):
    """Generate response to user query"""
    clean_old_conversations()

    # Greetings
    greetings = ['سلام', 'درود', 'صبح بخیر', 'hello', 'hi']
    if any(g in user_query.lower() for g in greetings) and len(user_query.split()) <= 3:
        return "سلام! 👋\n\nمن دستیار قوانین کتابخانه هستم.\nسوال خود را درباره قوانین، آیین‌نامه‌ها و مقررات کتابخانه بپرسید.\n\n**مثال:**\n• چطور کتاب اهدا کنم؟\n• شرایط استفاده از پایان‌نامه‌ها چیه؟\n• چطور فرم اهدا پر کنم؟"

    # Get history
    history = get_conversation_history(chat_id, limit=5)

    # Build messages for GPT
    messages = [
        {"role": "system", "content": regulations_handler.get_system_prompt()}
    ]

    # Add history
    for h in history:
        messages.append({
            "role": h["role"],
            "content": h["content"][:500]  # محدود کردن طول
        })

    # Add new query
    messages.append({"role": "user", "content": user_query})

    try:
        # Send to GPT
        response = openai_client.chat.completions.create(
            model=config.GPT_MODEL,
            messages=messages,
            max_tokens=800,
            temperature=0.3
        )

        assistant_response = response.choices[0].message.content

        # Save to memory
        add_to_conversation(chat_id, "user", user_query)
        add_to_conversation(chat_id, "assistant", assistant_response)

        return assistant_response

    except Exception as e:
        print(f"❌ Error generating response: {e}")
        return "متأسفم، مشکلی پیش آمد. لطفاً دوباره تلاش کنید."


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start command"""
    keyboard = [["🔄 مکالمه جدید"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    welcome_message = (
        "سلام! 👋\n\n"
        "به ربات قوانین و مقررات کتابخانه دانشگاه خوارزمی خوش آمدید! 📋\n\n"
        "من می‌توانم:\n"
        "✅ درباره قوانین کتابخانه پاسخ دهم\n"
        "✅ راهنمایی برای اهدای کتاب ارائه کنم\n"
        "✅ شرایط استفاده از پایان‌نامه‌ها را توضیح دهم\n\n"
        "**مثال‌های سوال:**\n"
        "• چطور می‌تونم کتاب اهدا کنم؟\n"
        "• شرایط دسترسی به پایان‌نامه‌ها چیه؟\n"
        "• برای تحویل پایان‌نامه چی نیاز دارم؟\n\n"
        "💡 حافظه مکالمه: 7 روز\n\n"
        "سوال خود را بپرسید! 😊"
    )

    await update.message.reply_text(welcome_message, reply_markup=reply_markup)


async def new_conversation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start new conversation"""
    chat_id = update.effective_chat.id
    conversation_memory.pop(chat_id, None)

    await update.message.reply_text(
        "✅ مکالمه جدید شروع شد!\n\n"
        "سوال جدید خود را بپرسید. 😊"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    help_text = (
        "📖 **راهنمای استفاده:**\n\n"
        "🔹 سوال خود را درباره قوانین بپرسید\n"
        "🔹 از دکمه‌های منو برای دسترسی سریع استفاده کنید\n"
        "🔹 برای مکالمه جدید: /new\n\n"
        "**مثال‌های سوال:**\n"
        "• چطور می‌تونم کتاب اهدا کنم؟\n"
        "• شرایط دسترسی به پایان‌نامه‌ها چیه؟\n"
        "• فرم اهدا کتاب کجاست؟\n"
        "• آیا می‌تونم از دانشگاه دیگه استفاده کنم؟"
    )

    await update.message.reply_text(help_text, parse_mode='Markdown')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process user message"""
    user_message = update.message.text
    chat_id = update.effective_chat.id

    # Handle new conversation button
    if user_message == "🔄 مکالمه جدید":
        await new_conversation_command(update, context)
        return

    # Show typing indicator
    await update.message.chat.send_action(action="typing")

    # Generate response
    response = generate_response(user_message, chat_id)

    # Send response
    await update.message.reply_text(response)


def main():
    """Start the bot"""
    print("=" * 60)
    print("🤖 Starting Library Regulations Bot")
    print("=" * 60)

    # Load regulations
    if not initialize_handler():
        print("❌ Initialization failed!")
        return

    # Create Application
    TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("new", new_conversation_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Regulations bot is ready!")
    print("=" * 60)

    # Start polling
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
