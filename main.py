import logging
import asyncio
import os
import sys
import io
import uuid
from typing import Tuple
import numpy as np
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from PIL import Image, ImageDraw, ImageFont, ImageColor
from moviepy import VideoFileClip
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    print("Error: BOT_TOKEN environment variable is not set.")
    sys.exit(1)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
user_settings = {}
DEFAULTS = {
    'text': '@KleimoRobot',
    'color': '#FFFFFF',
    'size': 30,
    'mode': 'single',
    'pos': 'br'
}
def get_user_settings(user_id):
    if user_id not in user_settings:
        user_settings[user_id] = DEFAULTS.copy()
    return user_settings[user_id]
def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    try:
        return ImageColor.getrgb(hex_color)
    except ValueError:
        return (255, 255, 255)
def create_watermark_image(base_size: Tuple[int, int], settings: dict, font_path: str = None) -> Image.Image:
    width, height = base_size
    text = settings['text']
    size = settings['size']
    color = hex_to_rgb(settings['color'])
    mode = settings['mode']
    pos = settings['pos']
    
    watermark_layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(watermark_layer)
    
    try:
        font_to_use = font_path if font_path and os.path.exists(font_path) else "arial.ttf"
        try:
            font = ImageFont.truetype(font_to_use, size)
        except OSError:
            font = ImageFont.load_default() 
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    rgba_color = (*color, 128)
    if mode == 'single':
        x, y = 0, 0
        padding = 20
        
        if pos == 'tl': x, y = padding, padding
        elif pos == 'tr': x, y = width - text_w - padding, padding
        elif pos == 'bl': x, y = padding, height - text_h - padding
        elif pos == 'br': x, y = width - text_w - padding, height - text_h - padding
        elif pos == 'center': x, y = (width - text_w) // 2, (height - text_h) // 2
            
        draw.text((x, y), text, font=font, fill=rgba_color)
        
    elif mode == 'multi':
        temp_txt_img = Image.new('RGBA', (int(width * 1.5), int(height * 1.5)), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_txt_img)
        
        step_x = text_w + 100
        step_y = text_h + 100
        
        for y in range(0, temp_txt_img.height, step_y):
            for x in range(0, temp_txt_img.width, step_x):
                temp_draw.text((x, y), text, font=font, fill=rgba_color)
        
        rotated = temp_txt_img.rotate(45, resample=Image.BICUBIC)
        
        cx, cy = rotated.width // 2, rotated.height // 2
        left = cx - width // 2
        top = cy - height // 2
        
        crop = rotated.crop((left, top, left + width, top + height))
        watermark_layer.paste(crop, (0, 0), crop)
    return watermark_layer
def process_image_in_memory(image_bytes: bytes, user_id: int, font_path: str = None) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as base_image:
        base_image = base_image.convert("RGBA")
        settings = get_user_settings(user_id)
        
        watermark = create_watermark_image(base_image.size, settings, font_path)
        
        result = Image.alpha_composite(base_image, watermark)
        result = result.convert("RGB")
        
        output = io.BytesIO()
        result.save(output, format="JPEG", quality=90)
        return output.getvalue()
def process_video_sync(input_path: str, output_path: str, user_id: int, font_path: str = None):
    clip = VideoFileClip(input_path)
    
    def process_frame(image):
        pil_img = Image.fromarray(image).convert("RGBA")
        settings = get_user_settings(user_id)
        watermark = create_watermark_image(pil_img.size, settings, font_path)
        result = Image.alpha_composite(pil_img, watermark)
        return np.array(result.convert("RGB"))
    new_clip = clip.image_transform(process_frame)
    
    new_clip.write_videofile(
        output_path, 
        codec='libx264', 
        audio_codec='aac', 
        remove_temp=True,
        verbose=False, 
        preset='medium' 
    )
    
    clip.close()
    new_clip.close()
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я @KleimoRobot.\\n"
        "Отправь мне фото или видео, и я наложу на него водяной знак.\\n\\n"
        "Настройки:\\n"
        "/text [текст] - сменить текст\\n"
        "/color [#RRGGBB] - цвет (HEX)\\n"
        "/size [число] - размер шрифта\\n"
        "/mode [single/multi] - режим\\n"
        "/pos [tl, tr, bl, br, center] - позиция\\n\\n"
        "Отправь .ttf файл, чтобы сменить шрифт."
    )
@dp.message(Command("text"))
async def cmd_text(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        get_user_settings(message.from_user.id)['text'] = args[1]
        await message.answer(f"Текст изменен на: {args[1]}")
    else:
        await message.answer("Пример: /text @MyChannel")
@dp.message(Command("color"))
async def cmd_color(message: types.Message):
    args = message.text.split()
    if len(args) > 1 and args[1].startswith('#') and len(args[1]) == 7:
        get_user_settings(message.from_user.id)['color'] = args[1]
        await message.answer(f"Цвет изменен на: {args[1]}")
    else:
        await message.answer("Пример: /color #FF0000")
@dp.message(Command("size"))
async def cmd_size(message: types.Message):
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        get_user_settings(message.from_user.id)['size'] = int(args[1])
        await message.answer(f"Размер изменен на: {args[1]}")
    else:
        await message.answer("Пример: /size 40")
@dp.message(Command("mode"))
async def cmd_mode(message: types.Message):
    args = message.text.split()
    if len(args) > 1 and args[1] in ['single', 'multi']:
        get_user_settings(message.from_user.id)['mode'] = args[1]
        await message.answer(f"Режим изменен на: {args[1]}")
    else:
        await message.answer("Пример: /mode multi")
@dp.message(Command("pos"))
async def cmd_pos(message: types.Message):
    args = message.text.split()
    valid_pos = ['tl', 'tr', 'bl', 'br', 'center']
    if len(args) > 1 and args[1] in valid_pos:
        get_user_settings(message.from_user.id)['pos'] = args[1]
        await message.answer(f"Позиция изменена на: {args[1]}")
    else:
        await message.answer(f"Доступные: {', '.join(valid_pos)}")
@dp.message(F.document)
async def handle_font(message: types.Message):
    if message.document.file_name.endswith('.ttf'):
        font_path = "user_font.ttf" 
        await bot.download(message.document, destination=font_path)
        await message.answer("Шрифт обновлен!")
    else:
        await message.answer("Пожалуйста, отправьте файл .ttf")
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    status_msg = await message.answer("Обрабатываю фото...")
    
    try:
        photo = message.photo[-1]
        file_io = io.BytesIO()
        await bot.download(photo, destination=file_io)
        file_io.seek(0)
        
        font_path = "user_font.ttf" if os.path.exists("user_font.ttf") else None
        
        processed_bytes = await asyncio.to_thread(
            process_image_in_memory, 
            file_io.getvalue(), 
            message.from_user.id,
            font_path
        )
        
        output_file = types.BufferedInputFile(processed_bytes, filename="watermarked.jpg")
        await message.answer_photo(output_file, caption="Готово!")
        
    except Exception as e:
        logger.error(f"Error processing photo: {e}")
        await message.answer("Ошибка при обработке фото.")
    finally:
        await status_msg.delete()
@dp.message(F.video)
async def handle_video(message: types.Message):
    video = message.video
    
    if video.file_size > 50 * 1024 * 1024:
        await message.answer("Видео слишком большое (лимит 50 МБ).")
        return
    if video.duration > 120:
        await message.answer("Видео слишком длинное (лимит 120 сек).")
        return
    status_msg = await message.answer("Видео обрабатывается, пожалуйста, подождите...")
    temp_input = f"temp_in_{uuid.uuid4()}.mp4"
    temp_output = f"temp_out_{uuid.uuid4()}.mp4"
    try:
        await bot.download(video, destination=temp_input)
        
        font_path = "user_font.ttf" if os.path.exists("user_font.ttf") else None
        user_id = message.from_user.id
        
        await asyncio.to_thread(
            process_video_sync, 
            temp_input, 
            temp_output, 
            user_id, 
            font_path
        )
        
        video_file = FSInputFile(temp_output)
        await message.answer_video(video_file, caption="Готово!")
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        await message.answer("Ошибка при обработке видео.")
        
    finally:
        if os.path.exists(temp_input):
            os.remove(temp_input)
        if os.path.exists(temp_output):
            os.remove(temp_output)
        await status_msg.delete()
async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
