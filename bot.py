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

# ==============================
# ENV VARIABLES
# ==============================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

# ==============================
# LOAD STUDENTS
# ==============================

with open("students.json", "r") as f:
    students = json.load(f)

selected_students = set()

# ==============================
# DATABASE
# ==============================

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

# ==============================
# COMMANDS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Dance Attendance Bot Running")

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_daily_prompt(context)

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await generate_report(context)

# ==============================
# DAILY PROMPT
# ==============================

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

# ==============================
# YES / NO RESPONSE
# ==============================

async def class_response(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if query.data == "class_no":
        await query.edit_message_text("No class recorded today.")
        return

    if query.data == "class_yes":
        await show_students(query)

# ==============================
# STUDENT BUTTONS (2 columns)
# ==============================

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

# ==============================
# TOGGLE STUDENT
# ==============================

async def toggle_student(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    student = query.data.replace("student_", "")

    if student in selected_students:
        selected_students.remove(student)
    else:
        selected_students.add(student)

    await show_students(query)

# ==============================
# SAVE ATTENDANCE
# ==============================

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
            pass  # prevents duplicate entries

    conn.commit()
    selected_students.clear()

    await query.edit_message_text("Attendance saved.")

# ==============================
# REPORT GENERATOR
# ==============================

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

    text = "Attendance Summary (Last 3 Months)\n\n"
    text += "Student  " + "  ".join(months) + "\n"

    for student in students:

        line = student + "  "

        for m in months:
            line += str(report.get(student, {}).get(m, 0)) + "  "

        text += line + "\n"

    await context.bot.send_message(chat_id=CHAT_ID, text=text)

# ==============================
# WEEKLY REPORT JOB
# ==============================

async def weekly_report(context: ContextTypes.DEFAULT_TYPE):
    await generate_report(context)

# ==============================
# MAIN
# ==============================

def main():

    app = ApplicationBuilder().token(TOKEN).build()

    job_queue = app.job_queue

    # Daily 9 PM IST
    job_queue.run_daily(
        send_daily_prompt,
        time=datetime.strptime("21:00", "%H:%M").time(),
        chat_id=CHAT_ID,
        name="daily_attendance",
    )

    # Sunday 9 PM IST
    job_queue.run_daily(
        weekly_report,
        time=datetime.strptime("21:00", "%H:%M").time(),
        days=(6,),
        chat_id=CHAT_ID,
        name="weekly_report",
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
