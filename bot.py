import os
import json
import sqlite3
import pytz
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# -----------------------------
# ENV VARIABLES
# -----------------------------

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

# -----------------------------
# LOAD STUDENTS
# -----------------------------

with open("students.json", "r") as f:
    students = json.load(f)

selected_students = set()

# -----------------------------
# DATABASE
# -----------------------------

conn = sqlite3.connect("attendance.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    student TEXT
)
""")

conn.commit()

# -----------------------------
# COMMANDS
# -----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Dance Attendance Bot Running")

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_daily_prompt(context)

# -----------------------------
# DAILY PROMPT
# -----------------------------

async def send_daily_prompt(context: ContextTypes.DEFAULT_TYPE):

    keyboard = [[
        InlineKeyboardButton("YES", callback_data="class_yes"),
        InlineKeyboardButton("NO", callback_data="class_no")
    ]]

    await context.bot.send_message(
        chat_id=CHAT_ID,
        text="Did class happen today?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# -----------------------------
# YES / NO RESPONSE
# -----------------------------

async def class_response(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if query.data == "class_no":
        await query.edit_message_text("No class recorded today.")
        return

    if query.data == "class_yes":
        await show_students(query)

# -----------------------------
# STUDENT BUTTONS
# -----------------------------

async def show_students(query):

    keyboard = []

    for student in students:

        label = student
        if student in selected_students:
            label = f"✅ {student}"

        keyboard.append([
            InlineKeyboardButton(label, callback_data=f"student_{student}")
        ])

    keyboard.append([
        InlineKeyboardButton("SUBMIT", callback_data="submit")
    ])

    await query.edit_message_text(
        "Select students present:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# -----------------------------
# TOGGLE STUDENTS
# -----------------------------

async def toggle_student(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    student = query.data.replace("student_", "")

    if student in selected_students:
        selected_students.remove(student)
    else:
        selected_students.add(student)

    await show_students(query)

# -----------------------------
# SAVE ATTENDANCE
# -----------------------------

async def submit_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    today = datetime.now().strftime("%Y-%m-%d")

    for student in selected_students:
        cursor.execute(
            "INSERT INTO attendance (date, student) VALUES (?, ?)",
            (today, student)
        )

    conn.commit()
    selected_students.clear()

    await query.edit_message_text("Attendance saved.")

# -----------------------------
# WEEKLY REPORT
# -----------------------------

async def weekly_report(context: ContextTypes.DEFAULT_TYPE):

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

    text = "Attendance Summary (Last 3 Months)\n\n"
    text += "Student  " + "  ".join(months) + "\n"

    for student in students:

        line = student + "  "

        for m in months:
            line += str(report.get(student, {}).get(m, 0)) + "  "

        text += line + "\n"

    await context.bot.send_message(chat_id=CHAT_ID, text=text)

# -----------------------------
# MAIN
# -----------------------------

def main():

    app = ApplicationBuilder().token(TOKEN).build()

    scheduler = AsyncIOScheduler(
        timezone=pytz.timezone("Asia/Kolkata")
    )

    scheduler.add_job(
        send_daily_prompt,
        "cron",
        hour=21,
        minute=0
    )

    scheduler.add_job(
        weekly_report,
        "cron",
        day_of_week="sun",
        hour=21,
        minute=0
    )

    scheduler.start()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test))

    app.add_handler(CallbackQueryHandler(class_response, pattern="class_"))
    app.add_handler(CallbackQueryHandler(toggle_student, pattern="student_"))
    app.add_handler(CallbackQueryHandler(submit_attendance, pattern="submit"))

    print("Bot running...")

    app.run_polling()

if __name__ == "__main__":
    main()
