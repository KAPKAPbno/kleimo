import asyncio
import logging
import io
import math
import os
from typing import Dict, Any

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command, CommandObject
from aiogram.fsm.storage.memory import MemoryStorage

from PIL import Image, ImageDraw, ImageFont, ImageColor

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================

# Хранилище настроек пользователей (в памяти)
user_settings: Dict[int, Dict[str, Any]] = {}

DEFAULT_SETTINGS = {
    'text': 'Watermark',
    'color': '#FFFFFF', # Белый
    'size': 40,
    'mode': 'single',   # single (один) или multi (плитка)
    'pos': 'br'         # br (низ-право) по умолчанию
}

router = Router()

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def get_settings(user_id: int) -> dict:
    """Получает настройки пользователя или создает дефолтные"""
    if user_id not in user_settings:
        user_settings[user_id] = DEFAULT_SETTINGS.copy()
    return user_settings[user_id]

# ==========================================
# ХЕНДЛЕРЫ КОМАНД
# ==========================================

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я бот для водяных знаков.\n\n"
        "📸 Как использовать:\n"
        "Просто отправь мне фото, и я наложу на него текст.\n"
        "Отправь файл шрифта (.ttf), чтобы сменить шрифт.\n\n"
        "⚙️ Настройки:\n"
        "/text [текст] — Текст ватермарки\n"
        "/color [hex] — Цвет (например, #FF0000)\n"
        "/size [число] — Размер шрифта\n"
        "/mode [single/multi] — Режим (один или плитка)\n"
        "/pos [tl, tr, bl, br, center] — Позиция (для single)",
        parse_mode="HTML"
    )

@router.message(Command("text"))
async def cmd_text(message: Message, command: CommandObject):
    if not command.args:
        await message.answer("⚠️ Использование: /text Ваш текст", parse_mode="HTML")
        return
    settings = get_settings(message.from_user.id)
    settings['text'] = command.args
    await message.answer(f"✅ Текст изменен на: {settings['text']}", parse_mode="HTML")

@router.message(Command("color"))
async def cmd_color(message: Message, command: CommandObject):
    if not command.args:
        await message.answer("⚠️ Использование: /color #RRGGBB", parse_mode="HTML")
        return
    try:
        ImageColor.getrgb(command.args) # Проверка валидности
        settings = get_settings(message.from_user.id)
        settings['color'] = command.args
        await message.answer(f"✅ Цвет изменен на: {settings['color']}", parse_mode="HTML")
    except ValueError:
        await message.answer("❌ Неверный формат цвета. Используйте HEX (например, #FF0000).")

@router.message(Command("size"))
async def cmd_size(message: Message, command: CommandObject):
    if not command.args or not command.args.isdigit():
        await message.answer("⚠️ Использование: /size [число]", parse_mode="HTML")
        return
    
    size = int(command.args)
    if 10 <= size <= 500:
        settings = get_settings(message.from_user.id)
        settings['size'] = size
        await message.answer(f"✅ Размер шрифта: {size}", parse_mode="HTML")
    else:
        await message.answer("❌ Размер должен быть от 10 до 500.")

@router.message(Command("mode"))
async def cmd_mode(message: Message, command: CommandObject):
    mode = command.args
    if mode not in ('single', 'multi'):
        await message.answer("⚠️ Использование: /mode single или /mode multi", parse_mode="HTML")
        return
    settings = get_settings(message.from_user.id)
    settings['mode'] = mode
    await message.answer(f"✅ Режим установлен: {mode}", parse_mode="HTML")

@router.message(Command("pos"))
async def cmd_pos(message: Message, command: CommandObject):
    pos = command.args
    valid_pos = ('tl', 'tr', 'bl', 'br', 'center')
    if pos not in valid_pos:
        await message.answer(f"⚠️ Доступные позиции: {', '.join(valid_pos)}")
        return
    settings = get_settings(message.from_user.id)
    settings['pos'] = pos
    await message.answer(f"✅ Позиция установлена: {pos}", parse_mode="HTML")

# ==========================================
# ОБРАБОТКА ФАЙЛОВ
# ==========================================

@router.message(F.document)
async def handle_document(message: Message, bot: Bot):
    # Простая проверка на шрифт
    if message.document.file_name.lower().endswith('.ttf'):
        file = await bot.get_file(message.document.file_id)
        # Сохраняем шрифт локально (в реальном боте лучше сохранять с уникальным именем для юзера)
        await bot.download_file(file.file_path, "font.ttf")
        await message.answer("✅ Шрифт обновлен! Теперь он будет использоваться для ватермарок.")
    else:
        await message.answer("ℹ️ Это документ. Отправьте фото как изображение (сжатое), чтобы наложить ватермарку.")

@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot):
    user_id = message.from_user.id
    settings = get_settings(user_id)
    
    status_msg = await message.answer("⏳ Обрабатываю...")
    
    try:
        # Скачиваем фото в память
        photo = message.photo[-1] # Самое высокое качество
        file = await bot.get_file(photo.file_id)
        file_data = await bot.download_file(file.file_path)
        
        # Pillow обработка
        with Image.open(file_data) as img:
            img = img.convert("RGBA")
            
            # Загрузка шрифта
            try:
                font = ImageFont.truetype("font.ttf", settings['size'])
            except OSError:
                # Если шрифт не найден, используем дефолтный (но он не масштабируется так же хорошо)
                font = ImageFont.load_default()
            
            # Слой для текста
            txt_layer = Image.new('RGBA', img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_layer)
            
            text = settings['text']
            color_rgb = ImageColor.getrgb(settings['color'])
            fill_color = color_rgb + (180,) # Добавляем прозрачность (0-255)
            
            # Размеры текста
            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            if settings['mode'] == 'single':
                x, y = 0, 0
                padding = int(img.width * 0.05) # 5% отступ
                pos = settings['pos']
                
                if pos == 'tl': # Top-Left
                    x, y = padding, padding
                elif pos == 'tr': # Top-Right
                    x = img.width - text_width - padding
                    y = padding
                elif pos == 'bl': # Bottom-Left
                    x = padding
                    y = img.height - text_height - padding
                elif pos == 'br': # Bottom-Right
                    x = img.width - text_width - padding
                    y = img.height - text_height - padding
                elif pos == 'center':
                    x = (img.width - text_width) // 2
                    y = (img.height - text_height) // 2
                    
                draw.text((x, y), text, font=font, fill=fill_color)
                
            else: # multi (плитка под 45 градусов)
                # Вычисляем диагональ и берем запас, чтобы при повороте текст покрывал все углы
                diagonal = int(math.sqrt(img.width**2 + img.height**2))
                canvas_size = int(diagonal * 1.5)
                
                # Создаем большой квадратный холст для паттерна
                txt_layer_rot = Image.new('RGBA', (canvas_size, canvas_size), (255, 255, 255, 0))
                draw_rot = ImageDraw.Draw(txt_layer_rot)
                
                gap = int(settings['size'] * 4) # Отступ между повторами
                
                # Рисуем сетку текста
                # Смещаем начало отрисовки, чтобы центрировать паттерн (опционально)
                for y in range(-50, canvas_size, text_height + gap):
                    for x in range(-50, canvas_size, text_width + gap):
                        draw_rot.text((x, y), text, font=font, fill=fill_color)
                
                # Поворачиваем слой с текстом
                txt_layer_rot = txt_layer_rot.rotate(45, resample=Image.BICUBIC)
                
                # Обрезаем по центру до размера исходного изображения
                left = (txt_layer_rot.width - img.width) // 2
                top = (txt_layer_rot.height - img.height) // 2
                txt_layer_rot = txt_layer_rot.crop((left, top, left + img.width, top + img.height))
                
                # Применяем повернутый слой
                txt_layer = txt_layer_rot

            # Накладываем текст на изображение
            out = Image.alpha_composite(img, txt_layer)
            
            # Сохраняем в буфер
            output_io = io.BytesIO()
            out.convert("RGB").save(output_io, format='JPEG', quality=95)
            output_io.seek(0)
            
            await message.answer_photo(
                BufferedInputFile(output_io.read(), filename="watermark.jpg"),
                caption="✅ Готово!"
            )
            
    except Exception as e:
        logging.error(f"Error processing image: {e}")
        await message.answer("❌ Произошла ошибка при обработке изображения.")
    finally:
        # Удаляем сообщение "Обрабатываю..."
        await bot.delete_message(message.chat.id, status_msg.message_id)

# ==========================================
# ЗАПУСК
# ==========================================
async def main():
    logging.basicConfig(level=logging.INFO)
    
    # Получаем токен из переменных окружения
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("Ошибка: переменная окружения BOT_TOKEN не установлена!")
        return

    bot = Bot(token=token)
    dp = Dispatcher(storage=MemoryStorage())
    
    dp.include_router(router)
    
    print("Бот запущен...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
