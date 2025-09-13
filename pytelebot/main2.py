import os
import logging
import sqlite3
import csv
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Patch
from io import BytesIO, StringIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы для типов событий
EVENT_TYPES = {
    'sleep': "Легла спать",
    'wake_up': "Встала утром",
    'breakfast': "Завтрак",
    'lunch': "Обед",
    'dinner': "Ужин",
    'workout_start': "Начала тренировку",
    'workout_end': "Закончила тренировку"
}

# Цвета для событий
EVENT_COLORS = {
    'sleep': '#1f77b4',        # синий
    'wake_up': '#ff7f0e',      # оранжевый
    'breakfast': '#2ca02c',    # зеленый
    'lunch': '#d62728',        # красный
    'dinner': '#9467bd',       # фиолетовый
    'workout_start': '#8c564b', # коричневый
    'workout_end': '#e377c2'   # розовый
}

class SleepTrackerBot:
    def __init__(self, db_path='sleep_tracker.db'):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_type TEXT,
                timestamp DATETIME
            )
        ''')
        conn.commit()
        conn.close()
    
    def save_event(self, user_id: int, event_type: str):
        """Сохранение события в базу данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute(
            'INSERT INTO events (user_id, event_type, timestamp) VALUES (?, ?, ?)',
            (user_id, event_type, timestamp)
        )
        conn.commit()
        conn.close()
        return timestamp
    
    def get_today_events(self, user_id: int):
        """Получение событий за сегодня"""
        conn = sqlite3.connect(self.db_path)
        today = datetime.now().strftime('%Y-%m-%d')
        
        query = '''
            SELECT event_type, timestamp 
            FROM events 
            WHERE user_id = ? AND date(timestamp) = date(?)
            ORDER BY timestamp
        '''
        
        df = pd.read_sql_query(query, conn, params=(user_id, today))
        conn.close()
        return df
    
    def get_week_events(self, user_id: int):
        """Получение событий за текущую неделю"""
        conn = sqlite3.connect(self.db_path)
        
        # Находим начало недели (понедельник)
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        start_of_week_str = start_of_week.strftime('%Y-%m-%d')
        
        query = '''
            SELECT event_type, timestamp 
            FROM events 
            WHERE user_id = ? AND date(timestamp) >= date(?)
            ORDER BY timestamp
        '''
        
        df = pd.read_sql_query(query, conn, params=(user_id, start_of_week_str))
        conn.close()
        return df
    
    def get_all_events(self, user_id: int):
        """Получение всех событий пользователя"""
        conn = sqlite3.connect(self.db_path)
        
        query = '''
            SELECT event_type, timestamp 
            FROM events 
            WHERE user_id = ?
            ORDER BY timestamp
        '''
        
        df = pd.read_sql_query(query, conn, params=(user_id,))
        conn.close()
        return df
    
    def create_timeline_plot(self, user_id: int):
        """Создание графика временной линии за сегодня"""
        df = self.get_today_events(user_id)
        
        if df.empty:
            return None
        
        # Преобразуем timestamp в datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Создаем график
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # Настройка временной оси
        today = datetime.now().date()
        start_time = datetime.combine(today, datetime.min.time())
        end_time = start_time + timedelta(days=1)
        
        ax.set_xlim(start_time, end_time)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        
        # Добавляем события на график
        y_pos = 1
        for _, row in df.iterrows():
            event_time = row['timestamp']
            event_type = row['event_type']
            
            ax.plot(event_time, y_pos, 'o', 
                   markersize=12, 
                   color=EVENT_COLORS.get(event_type, 'black'),
                   label=EVENT_TYPES[event_type])
            
            # Добавляем подпись
            ax.text(event_time, y_pos + 0.1, 
                   f"{EVENT_TYPES[event_type]}\n{event_time.strftime('%H:%M')}",
                   ha='center', va='bottom', fontsize=9)
            
            y_pos += 1
        
        # Настройка внешнего вида
        ax.set_yticks([])
        ax.set_title(f'Временная линия событий за {today.strftime("%d.%m.%Y")}')
        ax.grid(True, alpha=0.3)
        
        # Создаем легенду
        legend_elements = [Patch(facecolor=color, label=EVENT_TYPES[event_type])
                          for event_type, color in EVENT_COLORS.items()]
        ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1, 1))
        
        plt.tight_layout()
        
        # Сохраняем в буфер
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf
    
    def create_week_plot(self, user_id: int):
        """Создание графика событий за неделю"""
        df = self.get_week_events(user_id)
        
        if df.empty:
            return None
        
        # Преобразуем timestamp в datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        df['hour'] = df['timestamp'].dt.hour + df['timestamp'].dt.minute / 60
        
        # Находим диапазон дней недели
        min_day = df['day_of_week'].min()
        max_day = df['day_of_week'].max()
        
        # Создаем график
        fig, ax = plt.subplots(figsize=(14, 10))
        
        # Добавляем события на график
        for _, row in df.iterrows():
            event_type = row['event_type']
            day_of_week = row['day_of_week']
            hour = row['hour']
            
            ax.scatter(day_of_week, hour, 
                      s=150, 
                      color=EVENT_COLORS.get(event_type, 'black'),
                      alpha=0.7,
                      edgecolors='white',
                      linewidth=1)
        
        # Настройка осей
        days_of_week = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        ax.set_xlim(-0.5, 6.5)
        ax.set_ylim(0, 24)
        ax.set_xticks(range(7))
        ax.set_xticklabels(days_of_week)
        ax.set_yticks(range(0, 25, 2))
        ax.set_ylabel('Время (часы)')
        ax.set_xlabel('Дни недели')
        
        # Добавляем сетку
        ax.grid(True, alpha=0.3)
        
        # Добавляем заголовок
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        ax.set_title(f'События за неделю {start_of_week.strftime("%d.%m")} - {end_of_week.strftime("%d.%m.%Y")}')
        
        # Создаем легенду
        legend_elements = [Patch(facecolor=color, label=EVENT_TYPES[event_type])
                          for event_type, color in EVENT_COLORS.items()]
        ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1, 1))
        
        plt.tight_layout()
        
        # Сохраняем в буфер
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf
    
    def create_csv_data(self, user_id: int):
        """Создание CSV файла со всеми данными"""
        df = self.get_all_events(user_id)
        
        if df.empty:
            return None
        
        # Преобразуем timestamp в datetime для красивого форматирования
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = df['timestamp'].dt.strftime('%Y-%m-%d')
        df['time'] = df['timestamp'].dt.strftime('%H:%M:%S')
        df['event_name'] = df['event_type'].map(EVENT_TYPES)
        
        # Выбираем нужные колонки
        csv_df = df[['date', 'time', 'event_name', 'event_type', 'timestamp']]
        
        # Создаем CSV в памяти
        csv_buffer = StringIO()
        csv_df.to_csv(csv_buffer, index=False, encoding='utf-8')
        csv_buffer.seek(0)
        
        return csv_buffer

# Инициализация бота
bot = SleepTrackerBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_text = """
    👋 Привет! Я бот для отслеживания твоего распорядка дня.

    📊 Я помогу тебе отслеживать:
    • Время сна и пробуждения
    • Приемы пищи
    • Тренировки

    🎯 Используй кнопки ниже для записи событий или команды:
    /stats - статистика за сегодня
    /week_stats - статистика за неделю
    /all_data - все данные в CSV

    ❓ Нужна помощь? Используй /help
    """
    
    keyboard = create_main_keyboard()
    await update.message.reply_text(welcome_text, reply_markup=keyboard)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
    📖 Инструкция по использованию бота:

    🎯 Основные команды:
    /start - Начать работу с ботом
    /stats - Показать статистику за сегодня
    /week_stats - Показать статистику за неделю
    /all_data - Получить все данные в CSV
    /help - Показать эту справку

    📝 Как записывать события:
    • Используй кнопки для быстрой записи
    • Каждое событие сохраняется с текущим временем
    • Все данные хранятся только для твоих статистик

    📊 Статистика:
    • /stats - график событий за сегодня
    • /week_stats - график событий за неделю (дни vs время)
    • /all_data - полный CSV файл со всеми данными
    """
    
    await update.message.reply_text(help_text)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stats"""
    user_id = update.effective_user.id
    
    try:
        # Создаем график
        plot_buf = bot.create_timeline_plot(user_id)
        
        if plot_buf:
            await update.message.reply_photo(
                photo=plot_buf,
                caption="📊 Ваша статистика за сегодня"
            )
        else:
            await update.message.reply_text("📝 Сегодня еще не было записано ни одного события.")
    
    except Exception as e:
        logger.error(f"Error generating stats: {e}")
        await update.message.reply_text("❌ Произошла ошибка при генерации статистики.")

async def week_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /week_stats"""
    user_id = update.effective_user.id
    
    try:
        # Создаем график недельной статистики
        plot_buf = bot.create_week_plot(user_id)
        
        if plot_buf:
            await update.message.reply_photo(
                photo=plot_buf,
                caption="📈 Ваша статистика за неделю\n\n• По вертикали: время суток (часы)\n• По горизонтали: дни недели\n• Цветные точки: события"
            )
        else:
            await update.message.reply_text("📝 За эту неделю еще не было записано ни одного события.")
    
    except Exception as e:
        logger.error(f"Error generating week stats: {e}")
        await update.message.reply_text("❌ Произошла ошибка при генерации недельной статистики.")

async def all_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /all_data"""
    user_id = update.effective_user.id
    
    try:
        # Создаем CSV файл
        csv_buffer = bot.create_csv_data(user_id)
        
        if csv_buffer:
            # Создаем имя файла с текущей датой
            filename = f"sleep_tracker_data_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            
            await update.message.reply_document(
                document=csv_buffer,
                filename=filename,
                caption="📁 Все ваши данные в CSV формате\n\nСодержит все записанные события с датами и временем"
            )
        else:
            await update.message.reply_text("📝 У вас еще нет записанных событий.")
    
    except Exception as e:
        logger.error(f"Error generating CSV: {e}")
        await update.message.reply_text("❌ Произошла ошибка при генерации CSV файла.")

def create_main_keyboard():
    """Создание инлайн-клавиатуры"""
    keyboard = [
        [
            InlineKeyboardButton("Легла спать", callback_data='sleep'),
            InlineKeyboardButton("Встала утром", callback_data='wake_up')
        ],
        [
            InlineKeyboardButton("Завтрак", callback_data='breakfast'),
            InlineKeyboardButton("Обед", callback_data='lunch'),
            InlineKeyboardButton("Ужин", callback_data='dinner')
        ],
        [
            InlineKeyboardButton("Начала тренировку", callback_data='workout_start'),
            InlineKeyboardButton("Закончила тренировку", callback_data='workout_end')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    event_type = query.data
    
    if event_type in EVENT_TYPES:
        try:
            # Сохраняем событие
            timestamp = bot.save_event(user_id, event_type)
            
            # Форматируем время для ответа
            event_time = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            formatted_time = event_time.strftime('%H:%M:%S')
            
            # Отправляем подтверждение
            await query.edit_message_text(
                text=f"✅ {EVENT_TYPES[event_type]} записано в {formatted_time}",
                reply_markup=create_main_keyboard()
            )
            
        except Exception as e:
            logger.error(f"Error saving event: {e}")
            await query.edit_message_text(
                text="❌ Произошла ошибка при сохранении события",
                reply_markup=create_main_keyboard()
            )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла непредвиденная ошибка. Попробуйте еще раз."
        )

def main():
    """Основная функция запуска бота"""
    # Получаем токен из переменных окружения
    TOKEN = os.environ.get('BOT_TOKEN')
    
    if not TOKEN:
        logger.error("❌ BOT_TOKEN не установлен!")
        print("Пожалуйста, установите переменную BOT_TOKEN в настройках Railway")
        return
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("week_stats", week_stats))
    application.add_handler(CommandHandler("all_data", all_data))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запуск бота
    print("🚀 Бот запускается на Railway...")
    logger.info("Бот запущен успешно!")
    application.run_polling()


if __name__ == "__main__":
    main()