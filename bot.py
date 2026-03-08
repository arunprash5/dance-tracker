import os
import json
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

with open("students.json", "r") as f:
    students = json.load(f)

selected_students = set()

conn = sqlite3.connect("attendance.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
id INTEGER PRIMARY KEY AUTOINCREMENT,
date TEXT,
student TEXT,
UNIQUE(date, student)
)
""")

conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Dance Attendance Bot Running")

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_daily_prompt(context)

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await generate_report(context)

async def send_daily_prompt(context: ContextTypes.DEFAULT_TYPE):

    keyboard = [[
        InlineKeyboardButton("YES", callback_data="class_yes"),
        InlineKeyboardButton("NO", callback_data="class_no"),
    ]]

    await context.bot.send_message(
        chat_id=CHAT_ID,
        text="Did class happen today?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def class_response(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if query.data == "class_no":
        await query.edit_message_text("No class recorded today.")
        return

    if query.data == "class_yes":
        await show_students(query)

async def show_students(query):

    keyboard = []
    row = []

    for student in students:

        label = student
        if student in selected_students:
            label = f"✅ {student}"

        row.append(
            InlineKeyboardButton(label, callback_data=f"student_{student}")
        )

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append(
        [InlineKeyboardButton("SUBMIT", callback_data="submit")]
    )

    await query.edit_message_text(
        "Select students present:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def toggle_student(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    student = query.data.replace("student_", "")

    if student in selected_students:
        selected_students.remove(student)
    else:
        selected_students.add(student)

    await show_students(query)

async def submit_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    today = datetime.now().strftime("%Y-%m-%d")

    for student in selected_students:

        try:
            cursor.execute(
                "INSERT INTO attendance (date, student) VALUES (?, ?)",
                (today, student),
            )
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    selected_students.clear()

    await query.edit_message_text("Attendance saved.")

async def generate_report(context: ContextTypes.DEFAULT_TYPE):

    cursor.execute("""
    SELECT student, strftime('%Y-%m', date) as month, COUNT(*)
    FROM attendance
    WHERE date >= date('now','-3 months')
    GROUP BY student, month
    """)

    rows = cursor.fetchall()

    report = {}
    months = set()

    for student, month, count in rows:

        months.add(month)

        if student not in report:
            report[student] = {}

        report[student][month] = count

    months = sorted(months)

    col_width = 10

    border = "+" + "-"*12 + "+"
    for m in months:
        border += "-"*(col_width) + "+"

    header = "| Student".ljust(13) + "|"
    for m in months:
        header += m.center(col_width) + "|"

    lines = [border, header, border]

    for student in students:

        row = "| " + student.ljust(10) + "|"

        for m in months:
            count = report.get(student, {}).get(m, 0)
            row += str(count).center(col_width) + "|"

        lines.append(row)

    lines.append(border)

    table = "\n".join(lines)

    message = "Attendance Summary (Last 3 Months)\n\n```\n" + table + "\n```"

    await context.bot.send_message(
        chat_id=CHAT_ID,
        text=message,
        parse_mode="Markdown"
    )

async def weekly_report(context: ContextTypes.DEFAULT_TYPE):
    await generate_report(context)

def main():

    app = ApplicationBuilder().token(TOKEN).build()

    job_queue = app.job_queue

    job_queue.run_daily(
        send_daily_prompt,
        time=datetime.strptime("21:00", "%H:%M").time(),
        chat_id=CHAT_ID,
    )

    job_queue.run_daily(
        weekly_report,
        time=datetime.strptime("21:00", "%H:%M").time(),
        days=(6,),
        chat_id=CHAT_ID,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test))
    app.add_handler(CommandHandler("report", report))

    app.add_handler(CallbackQueryHandler(class_response, pattern="class_"))
    app.add_handler(CallbackQueryHandler(toggle_student, pattern="student_"))
    app.add_handler(CallbackQueryHandler(submit_attendance, pattern="submit"))

    print("Bot running...")

    app.run_polling()

if __name__ == "__main__":
    main()
