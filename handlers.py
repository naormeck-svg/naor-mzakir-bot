async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Full bot reset with double confirmation."""
    chat_id = update.effective_chat.id
    total = db.count_items_by_type(chat_id, "all")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ כן, איפוס מלא", callback_data="clear_confirm:all")],
        [InlineKeyboardButton("❌ ביטול", callback_data="clear_cancel")],
    ])
    await update.effective_message.reply_text(
        f"🗂 *איפוס בוט*\nיש לך {total} פריטים שמורים.\n\nהאם אתה רוצה למחוק הכל?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show clear menu with type selection."""
    chat_id = update.effective_chat.id
    tasks = db.count_items_by_type(chat_id, "task")
    reminders = db.count_items_by_type(chat_id, "reminder")
    notes = db.count_items_by_type(chat_id, "note")
    total = tasks + reminders + notes
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📋 משימות ({tasks})", callback_data="clear_confirm:task"),
         InlineKeyboardButton(f"⏰ תזכורות ({reminders})", callback_data="clear_confirm:reminder")],
        [InlineKeyboardButton(f"📝 הערות ({notes})", callback_data="clear_confirm:note"),
         InlineKeyboardButton(f"💥 הכל ({total})", callback_data="clear_confirm:all")],
        [InlineKeyboardButton("❌ ביטול", callback_data="clear_cancel")],
    ])
    await update.effective_message.reply_text(
        "🗂 *מה תרצה למחוק?*",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
