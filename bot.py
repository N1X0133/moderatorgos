import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import datetime
import logging
import json
import os
import aiofiles
from typing import Optional

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ID главного администратора (зафиксирован)
MAIN_ADMIN_ID = 927642459998138418

# ID вашего сервера и каналов
YOUR_GUILD_ID = 886219875452854292  # ID сервера
WELCOME_CHANNEL_ID = 886221288421589004  # Канал для приветствий
CURATOR_CHANNEL_ID = 1178309021065809951  # Канал с кураторами
BALANCE_CHANNEL_ID = 1444397866499182665  # Канал с балловой системой

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.moderation = True
intents.voice_states = True

class ModerationBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.initial_extensions = []
        
    async def setup_hook(self):
        # Синхронизация слеш-команд
        await self.tree.sync()
        logger.info("✅ Слеш-команды синхронизированы")
        
    async def on_ready(self):
        # Информационная панель при запуске
        print("\n" + "="*50)
        print("🤖 МОДЕРАЦИОННЫЙ БОТ ЗАПУЩЕН")
        print("="*50)
        print(f"📱 Имя бота: {self.user.name}")
        print(f"🆔 ID бота: {self.user.id}")
        print(f"🌐 Серверов: {len(self.guilds)}")
        print(f"👑 Главный администратор: {MAIN_ADMIN_ID}")
        print(f"👨‍💻 Автор: by Ilya Vetrov")
        print(f"📅 Время запуска: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
        print("="*50 + "\n")
        
        await self.change_presence(activity=discord.Game(name="/help | Модерация by Ilya Vetrov"))

bot = ModerationBot()

# ЗАЩИЩЕННАЯ ПАПКА ДЛЯ ДАННЫХ
DATA_DIR = '/app/data'
os.makedirs(DATA_DIR, exist_ok=True)

# Файлы в защищенной папке
JOIN_ROLES_FILE = os.path.join(DATA_DIR, 'join_roles.json')
LOG_CHANNELS_FILE = os.path.join(DATA_DIR, 'log_channels.json')
MOD_LOGS_FILE = os.path.join(DATA_DIR, 'mod_logs.json')
WARNS_FILE = os.path.join(DATA_DIR, 'warns.json')

# Дублируем в корень для совместимости
LOCAL_JOIN_ROLES = 'join_roles.json'
LOCAL_LOG_CHANNELS = 'log_channels.json'
LOCAL_MOD_LOGS = 'mod_logs.json'
LOCAL_WARNS = 'warns.json'

# ==================== СИСТЕМА ХРАНЕНИЯ ДАННЫХ ====================

class DataManager:
    def __init__(self):
        self.data_folder = DATA_DIR
        self.ensure_data_folder()
        
    def ensure_data_folder(self):
        if not os.path.exists(self.data_folder):
            os.makedirs(self.data_folder)
            logger.info(f"📁 Создана папка {self.data_folder}")
    
    def save_data(self, filename, local_filename, data):
        try:
            filepath = os.path.join(self.data_folder, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            with open(local_filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                
            logger.info(f"💾 Данные сохранены в {filename}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения {filename}: {e}")
            return False
    
    def load_data(self, filename, local_filename, default=None):
        filepath = os.path.join(self.data_folder, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки {filename}: {e}")
        
        if os.path.exists(local_filename):
            try:
                with open(local_filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.save_data(filename, local_filename, data)
                return data
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки {local_filename}: {e}")
        
        return default if default is not None else {}

data_manager = DataManager()

# ==================== КЛАССЫ ДЛЯ ХРАНЕНИЯ ДАННЫХ ====================

class GuildSettings:
    def __init__(self):
        self.join_roles = {}
        self.log_channels = {
            "mod_actions": {},
            "message_delete": {},
            "message_edit": {},
            "bulk_delete": {},
            "role_give": {},
            "warns": {},
            "voice": {},
            "nickname": {}
        }
        self.mod_logs = {}
        self.warns = {}
        
    def load_all(self):
        self.join_roles = data_manager.load_data('join_roles.json', LOCAL_JOIN_ROLES, {})
        
        loaded_channels = data_manager.load_data('log_channels.json', LOCAL_LOG_CHANNELS, {})
        for key in self.log_channels.keys():
            if key in loaded_channels:
                self.log_channels[key] = {int(k) if k.isdigit() else k: v for k, v in loaded_channels[key].items()}
        
        self.mod_logs = data_manager.load_data('mod_logs.json', LOCAL_MOD_LOGS, {})
        self.warns = data_manager.load_data('warns.json', LOCAL_WARNS, {})
        
        self.join_roles = {int(k) if isinstance(k, str) and k.isdigit() else k: v for k, v in self.join_roles.items()}
        self.mod_logs = {int(k) if isinstance(k, str) and k.isdigit() else k: v for k, v in self.mod_logs.items()}
        self.warns = {int(k) if isinstance(k, str) and k.isdigit() else k: v for k, v in self.warns.items()}
        
        logger.info(f"📂 Загружено: join_roles: {len(self.join_roles)}")
        
    def save_join_roles(self):
        data_manager.save_data('join_roles.json', LOCAL_JOIN_ROLES, self.join_roles)
        
    def save_log_channels(self):
        data_manager.save_data('log_channels.json', LOCAL_LOG_CHANNELS, self.log_channels)
        
    def save_mod_logs(self):
        data_manager.save_data('mod_logs.json', LOCAL_MOD_LOGS, self.mod_logs)
        
    def save_warns(self):
        data_manager.save_data('warns.json', LOCAL_WARNS, self.warns)

settings = GuildSettings()

# ==================== ПРОВЕРКА ПРАВ ====================

def is_admin_only():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.id == MAIN_ADMIN_ID:
            return True
        if interaction.user.guild_permissions.administrator:
            return True
        raise app_commands.errors.MissingPermissions(["administrator"])
    return app_commands.check(predicate)

# ==================== ФУНКЦИИ ДЛЯ ОТПРАВКИ В РАЗНЫЕ КАНАЛЫ ====================

async def send_to_log_channel(guild, log_type, embed):
    if not guild:
        return
    
    guild_id = str(guild.id)
    if guild_id in settings.log_channels.get(log_type, {}):
        channel_id = settings.log_channels[log_type][guild_id]
        channel = guild.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(embed=embed)
                logger.info(f"📤 Отправлен лог в канал {channel.name} (тип: {log_type})")
            except Exception as e:
                logger.error(f"Ошибка отправки в канал {log_type}: {e}")
    else:
        logger.info(f"[{log_type}] {embed.description if hasattr(embed, 'description') else embed.title}")

async def log_mod_action(guild, action_description, color=discord.Color.blue()):
    embed = discord.Embed(
        description=action_description,
        color=color,
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="by Ilya Vetrov • Модерация")
    await send_to_log_channel(guild, "mod_actions", embed)

async def log_role_give(guild, action_description, color=discord.Color.green()):
    embed = discord.Embed(
        description=action_description,
        color=color,
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="by Ilya Vetrov • Изменение ролей")
    await send_to_log_channel(guild, "role_give", embed)

async def log_warn(guild, action_description):
    embed = discord.Embed(
        description=action_description,
        color=discord.Color.yellow(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="by Ilya Vetrov • Предупреждения")
    await send_to_log_channel(guild, "warns", embed)

async def log_voice(guild, action_description, color=discord.Color.purple()):
    embed = discord.Embed(
        description=action_description,
        color=color,
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="by Ilya Vetrov • Голосовые каналы")
    await send_to_log_channel(guild, "voice", embed)

async def log_nickname(guild, action_description):
    embed = discord.Embed(
        description=action_description,
        color=discord.Color.teal(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="by Ilya Vetrov • Смена ника")
    await send_to_log_channel(guild, "nickname", embed)

async def log_message_delete(guild, message):
    """Логирование удаленного сообщения"""
    if not guild:
        return
    
    guild_id = str(guild.id)
    if guild_id in settings.log_channels.get("message_delete", {}):
        channel_id = settings.log_channels["message_delete"][guild_id]
        channel = guild.get_channel(int(channel_id))
        if channel:
            embed = discord.Embed(
                title="🗑 СООБЩЕНИЕ УДАЛЕНО",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            
            author_text = f"{message.author.mention}\nID: `{message.author.id}`\nИмя: `{message.author.name}`"
            embed.add_field(name="👤 Автор", value=author_text, inline=True)
            
            channel_text = f"{message.channel.mention}\nID: `{message.channel.id}`"
            embed.add_field(name="📌 Канал", value=channel_text, inline=True)
            
            if message.created_at:
                time_text = message.created_at.strftime("%d.%m.%Y %H:%M:%S")
                embed.add_field(name="⏰ Отправлено", value=f"`{time_text}`", inline=True)
            
            if message.content:
                content = message.content[:1000] + "..." if len(message.content) > 1000 else message.content
                embed.add_field(name="📝 Содержание", value=f"```{content}```", inline=False)
            else:
                embed.add_field(name="📝 Содержание", value="`[Пустое сообщение]`", inline=False)
            
            if message.attachments:
                attachments_list = []
                for i, att in enumerate(message.attachments, 1):
                    attachments_list.append(f"{i}. [{att.filename}]({att.url}) ({(att.size/1024):.1f} KB)")
                attachments_text = "\n".join(attachments_list)
                embed.add_field(name="📎 Вложения", value=attachments_text[:1000], inline=False)
            
            embed.set_footer(text=f"by Ilya Vetrov • ID сообщения: {message.id}")
            await channel.send(embed=embed)

# ==================== КОМАНДА ДЛЯ ТЕСТА ЛОГОВ РОЛЕЙ ====================

@bot.tree.command(name="test_role_log", description="Протестировать логирование ролей (выдать тестовую роль)")
@is_admin_only()
async def slash_test_role_log(interaction: discord.Interaction):
    """Тестовая команда для проверки логирования ролей"""
    await interaction.response.defer(ephemeral=True)
    
    # Проверяем настроен ли канал для логов ролей
    guild_id = str(interaction.guild_id)
    if guild_id in settings.log_channels.get("role_give", {}):
        channel_id = settings.log_channels["role_give"][guild_id]
        channel = interaction.guild.get_channel(int(channel_id))
        if channel:
            # Отправляем тестовый лог
            test_embed = discord.Embed(
                title="🧪 ТЕСТ ЛОГИРОВАНИЯ РОЛЕЙ",
                description=f"Это тестовое сообщение для проверки канала логов ролей.\n\n"
                            f"**Канал:** {channel.mention}\n"
                            f"**ID канала:** `{channel.id}`\n\n"
                            f"Если вы видите это сообщение, то канал настроен правильно!",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.utcnow()
            )
            test_embed.set_footer(text="by Ilya Vetrov • Тест логов ролей")
            await channel.send(embed=test_embed)
            
            await interaction.followup.send(f"✅ Тестовое сообщение отправлено в канал {channel.mention}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Канал с ID `{channel_id}` не найден!", ephemeral=True)
    else:
        await interaction.followup.send("❌ Канал для логов ролей не настроен! Используйте `/set_role_give_channel #канал`", ephemeral=True)

# ==================== КОМАНДА ДЛЯ БЫСТРОЙ НАСТРОЙКИ ВСЕХ КАНАЛОВ ====================

@bot.tree.command(name="setup_all_logs", description="Быстрая настройка всех каналов для логов (укажите канал)")
@app_commands.describe(channel="Канал для всех логов")
@is_admin_only()
async def slash_setup_all_logs(interaction: discord.Interaction, channel: discord.TextChannel):
    """Устанавливает один канал для всех типов логов"""
    guild_id = str(interaction.guild_id)
    
    for log_type in settings.log_channels.keys():
        settings.log_channels[log_type][guild_id] = channel.id
    
    settings.save_log_channels()
    
    embed = discord.Embed(
        title="✅ ВСЕ КАНАЛЫ ЛОГОВ НАСТРОЕНЫ",
        description=f"Все логи будут отправляться в {channel.mention}\n\n"
                    f"**Настроенные типы логов:**\n"
                    f"• 🛡️ Действия модерации\n"
                    f"• 🗑️ Удаленные сообщения\n"
                    f"• ✏️ Измененные сообщения\n"
                    f"• 📦 Массовые удаления\n"
                    f"• 👥 Выдача/снятие ролей\n"
                    f"• ⚠️ Предупреждения\n"
                    f"• 🔊 Голосовые каналы\n"
                    f"• 📝 Смена никнеймов",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

# ==================== СЛЕШ-КОМАНДЫ ДЛЯ НАСТРОЙКИ КАНАЛОВ ====================

@bot.tree.command(name="set_mod_log_channel", description="Установить канал для логов действий модерации")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_mod_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    settings.log_channels["mod_actions"][str(interaction.guild_id)] = channel.id
    settings.save_log_channels()
    
    embed = discord.Embed(
        title="✅ Канал для модерации установлен",
        description=f"Действия модерации будут логироваться в {channel.mention}",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_message_delete_channel", description="Установить канал для логов удаленных сообщений")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_message_delete_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    settings.log_channels["message_delete"][str(interaction.guild_id)] = channel.id
    settings.save_log_channels()
    
    embed = discord.Embed(
        title="✅ Канал для удаленных сообщений установлен",
        description=f"Удаленные сообщения будут логироваться в {channel.mention}",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_message_edit_channel", description="Установить канал для логов измененных сообщений")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_message_edit_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    settings.log_channels["message_edit"][str(interaction.guild_id)] = channel.id
    settings.save_log_channels()
    
    embed = discord.Embed(
        title="✅ Канал для измененных сообщений установлен",
        description=f"Измененные сообщения будут логироваться в {channel.mention}",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_bulk_delete_channel", description="Установить канал для логов массовых удалений")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_bulk_delete_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    settings.log_channels["bulk_delete"][str(interaction.guild_id)] = channel.id
    settings.save_log_channels()
    
    embed = discord.Embed(
        title="✅ Канал для массовых удалений установлен",
        description=f"Массовые удаления будут логироваться в {channel.mention}",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_role_give_channel", description="Установить канал для логов выдачи/снятия ролей")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_role_give_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    settings.log_channels["role_give"][str(interaction.guild_id)] = channel.id
    settings.save_log_channels()
    
    embed = discord.Embed(
        title="✅ Канал для изменений ролей установлен",
        description=f"Выдача и снятие ролей будут логироваться в {channel.mention}\n\n"
                    f"⚠️ **Важно:** Убедитесь, что бот имеет право **«Просматривать аудит логов»** (View Audit Log) на сервере!",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_warns_channel", description="Установить канал для логов предупреждений")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_warns_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    settings.log_channels["warns"][str(interaction.guild_id)] = channel.id
    settings.save_log_channels()
    
    embed = discord.Embed(
        title="✅ Канал для предупреждений установлен",
        description=f"Предупреждения будут логироваться в {channel.mention}",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_voice_channel", description="Установить канал для логов голосовых каналов")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_voice_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    settings.log_channels["voice"][str(interaction.guild_id)] = channel.id
    settings.save_log_channels()
    
    embed = discord.Embed(
        title="✅ Канал для голосовых каналов установлен",
        description=f"Входы/выходы из войс-каналов будут логироваться в {channel.mention}",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_nickname_channel", description="Установить канал для логов смены никнеймов")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_nickname_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    settings.log_channels["nickname"][str(interaction.guild_id)] = channel.id
    settings.save_log_channels()
    
    embed = discord.Embed(
        title="✅ Канал для смены никнеймов установлен",
        description=f"Смена никнеймов будет логироваться в {channel.mention}",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="show_log_channels", description="Показать настроенные каналы для логов")
@is_admin_only()
async def slash_show_log_channels(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    
    embed = discord.Embed(
        title="📋 Настроенные каналы логирования",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
    )
    
    channel_types = {
        "mod_actions": "🛡️ Действия модерации",
        "message_delete": "🗑️ Удаленные сообщения",
        "message_edit": "✏️ Измененные сообщения",
        "bulk_delete": "📦 Массовые удаления",
        "role_give": "👥 Изменение ролей",
        "warns": "⚠️ Предупреждения",
        "voice": "🔊 Голосовые каналы",
        "nickname": "📝 Смена никнеймов"
    }
    
    configured = 0
    for key, name in channel_types.items():
        if guild_id in settings.log_channels.get(key, {}):
            channel_id = settings.log_channels[key][guild_id]
            channel = interaction.guild.get_channel(int(channel_id))
            if channel:
                embed.add_field(name=name, value=channel.mention, inline=False)
                configured += 1
            else:
                embed.add_field(name=name, value=f"❌ Канал не найден (ID: {channel_id})", inline=False)
        else:
            embed.add_field(name=name, value="❌ Не настроен", inline=False)
    
    embed.add_field(name="📊 Статистика", value=f"Настроено {configured} из {len(channel_types)} каналов", inline=False)
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

# ==================== СЛЕШ-КОМАНДЫ ДЛЯ РОЛЕЙ ====================

@bot.tree.command(name="set_join_role", description="Установить роль для новых участников")
@app_commands.describe(role="Роль, которая будет выдаваться новым участникам")
@is_admin_only()
async def slash_set_join_role(interaction: discord.Interaction, role: discord.Role):
    settings.join_roles[str(interaction.guild_id)] = role.id
    settings.save_join_roles()
    
    embed = discord.Embed(
        title="✅ Роль установлена",
        description=f"Новые участники теперь будут получать роль {role.mention}",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
    await interaction.response.send_message(embed=embed)
    await log_role_give(interaction.guild, f"⚙️ {interaction.user.mention} (`{interaction.user.id}`) установил автоматическую выдачу роли {role.mention} для новичков", discord.Color.blue())

@bot.tree.command(name="remove_join_role", description="Отключить автоматическую выдачу роли")
@is_admin_only()
async def slash_remove_join_role(interaction: discord.Interaction):
    if str(interaction.guild_id) in settings.join_roles:
        del settings.join_roles[str(interaction.guild_id)]
        settings.save_join_roles()
        
        embed = discord.Embed(
            title="✅ Автовыдача отключена",
            description="Новые участники больше не будут получать роль автоматически",
            color=discord.Color.green()
        )
        embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
        await interaction.response.send_message(embed=embed)
        await log_role_give(interaction.guild, f"⚙️ {interaction.user.mention} (`{interaction.user.id}`) отключил автовыдачу роли", discord.Color.blue())
    else:
        await interaction.response.send_message("❌ Автовыдача роли не была настроена", ephemeral=True)

# ==================== СЛЕШ-КОМАНДЫ МОДЕРАЦИИ ====================

@bot.tree.command(name="kick", description="Кикнуть пользователя")
@app_commands.describe(member="Пользователь для кика", reason="Причина кика")
@is_admin_only()
async def slash_kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    try:
        await member.kick(reason=reason)
        
        embed = discord.Embed(
            title="👢 Пользователь кикнут",
            description=f"**Пользователь:** {member.mention}\n**ID:** `{member.id}`\n**Причина:** {reason}",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Модератор: {interaction.user} (`{interaction.user.id}`) • by Ilya Vetrov")
        await interaction.response.send_message(embed=embed)
        
        await log_mod_action(interaction.guild, f"👢 {interaction.user.mention} (`{interaction.user.id}`) кикнул {member.mention} (`{member.id}`)\nПричина: {reason}")
        await save_mod_log(interaction.guild, "kick", interaction.user, member, reason)
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="ban", description="Забанить пользователя")
@app_commands.describe(member="Пользователь для бана", reason="Причина бана")
@is_admin_only()
async def slash_ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    try:
        await member.ban(reason=reason, delete_message_days=0)
        
        embed = discord.Embed(
            title="🔨 Пользователь забанен",
            description=f"**Пользователь:** {member.mention}\n**ID:** `{member.id}`\n**Причина:** {reason}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Модератор: {interaction.user} (`{interaction.user.id}`) • by Ilya Vetrov")
        await interaction.response.send_message(embed=embed)
        
        await log_mod_action(interaction.guild, f"🔨 {interaction.user.mention} (`{interaction.user.id}`) забанил {member.mention} (`{member.id}`)\nПричина: {reason}")
        await save_mod_log(interaction.guild, "ban", interaction.user, member, reason)
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="unban", description="Разбанить пользователя по ID")
@app_commands.describe(user_id="ID пользователя", reason="Причина разбана")
@is_admin_only()
async def slash_unban(interaction: discord.Interaction, user_id: str, reason: str = "Не указана"):
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=reason)
        
        embed = discord.Embed(
            title="🔓 Пользователь разбанен",
            description=f"**Пользователь:** {user.name}\n**ID:** `{user.id}`\n**Причина:** {reason}",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Модератор: {interaction.user} (`{interaction.user.id}`) • by Ilya Vetrov")
        await interaction.response.send_message(embed=embed)
        
        await log_mod_action(interaction.guild, f"🔓 {interaction.user.mention} (`{interaction.user.id}`) разбанил {user.name} (`{user.id}`)\nПричина: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="mute", description="Замутить пользователя")
@app_commands.describe(member="Пользователь для мута", minutes="Длительность в минутах", reason="Причина мута")
@is_admin_only()
async def slash_mute(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Не указана"):
    try:
        duration = datetime.timedelta(minutes=minutes)
        await member.timeout(duration, reason=reason)
        
        embed = discord.Embed(
            title="🔇 Пользователь замучен",
            description=f"**Пользователь:** {member.mention}\n**ID:** `{member.id}`\n**Длительность:** {minutes} мин\n**Причина:** {reason}",
            color=discord.Color.dark_gray(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Модератор: {interaction.user} (`{interaction.user.id}`) • by Ilya Vetrov")
        await interaction.response.send_message(embed=embed)
        
        await log_mod_action(interaction.guild, f"🔇 {interaction.user.mention} (`{interaction.user.id}`) замутил {member.mention} (`{member.id}`) на {minutes} мин\nПричина: {reason}")
        await save_mod_log(interaction.guild, "mute", interaction.user, member, reason, minutes)
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="Снять мут с пользователя")
@app_commands.describe(member="Пользователь для снятия мута", reason="Причина")
@is_admin_only()
async def slash_unmute(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    try:
        await member.timeout(None, reason=reason)
        
        embed = discord.Embed(
            title="🔊 Мут снят",
            description=f"**Пользователь:** {member.mention}\n**ID:** `{member.id}`\n**Причина:** {reason}",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Модератор: {interaction.user} (`{interaction.user.id}`) • by Ilya Vetrov")
        await interaction.response.send_message(embed=embed)
        
        await log_mod_action(interaction.guild, f"🔊 {interaction.user.mention} (`{interaction.user.id}`) снял мут с {member.mention} (`{member.id}`)\nПричина: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="clear", description="Очистить сообщения в канале")
@app_commands.describe(amount="Количество сообщений для удаления")
@is_admin_only()
async def slash_clear(interaction: discord.Interaction, amount: int):
    try:
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        
        embed = discord.Embed(
            title="🧹 Сообщения удалены",
            description=f"Удалено **{len(deleted)}** сообщений",
            color=discord.Color.blue()
        )
        embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        await log_mod_action(interaction.guild, f"🧹 {interaction.user.mention} (`{interaction.user.id}`) очистил {len(deleted)} сообщений в {interaction.channel.mention}")
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="warn", description="Выдать предупреждение пользователю")
@app_commands.describe(member="Пользователь", reason="Причина предупреждения")
@is_admin_only()
async def slash_warn(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    guild_id = str(interaction.guild_id)
    
    if guild_id not in settings.warns:
        settings.warns[guild_id] = {}
    
    user_id = str(member.id)
    if user_id not in settings.warns[guild_id]:
        settings.warns[guild_id][user_id] = []
    
    warn_data = {
        "moderator": interaction.user.id,
        "reason": reason,
        "date": datetime.datetime.utcnow().isoformat()
    }
    settings.warns[guild_id][user_id].append(warn_data)
    settings.save_warns()
    
    embed = discord.Embed(
        title="⚠️ Предупреждение",
        description=f"**Пользователь:** {member.mention}\n**ID:** `{member.id}`\n**Предупреждений:** {len(settings.warns[guild_id][user_id])}\n**Причина:** {reason}",
        color=discord.Color.yellow(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text=f"Модератор: {interaction.user} (`{interaction.user.id}`) • by Ilya Vetrov")
    await interaction.response.send_message(embed=embed)
    
    try:
        await member.send(f"Вы получили предупреждение на сервере **{interaction.guild.name}**\n**Причина:** {reason}")
    except:
        pass
    
    await log_warn(interaction.guild, f"⚠️ {interaction.user.mention} (`{interaction.user.id}`) выдал предупреждение {member.mention} (`{member.id}`)\nПричина: {reason}")

@bot.tree.command(name="warns", description="Показать предупреждения пользователя")
@app_commands.describe(member="Пользователь")
@is_admin_only()
async def slash_warns(interaction: discord.Interaction, member: discord.Member):
    guild_id = str(interaction.guild_id)
    
    if guild_id in settings.warns and str(member.id) in settings.warns[guild_id]:
        warns = settings.warns[guild_id][str(member.id)]
        
        embed = discord.Embed(
            title=f"Предупреждения: {member.display_name}",
            description=f"**ID:** `{member.id}`",
            color=discord.Color.orange()
        )
        embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
        
        for i, warn in enumerate(warns[-10:], 1):
            mod = bot.get_user(warn["moderator"])
            mod_name = mod.name if mod else f"ID: {warn['moderator']}"
            date = datetime.datetime.fromisoformat(warn["date"]).strftime("%d.%m.%Y %H:%M")
            embed.add_field(
                name=f"#{i} - {date}",
                value=f"**Модератор:** {mod_name} (`{warn['moderator']}`)\n**Причина:** {warn['reason']}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(f"У пользователя {member.mention} нет предупреждений", ephemeral=True)

@bot.tree.command(name="mod_logs", description="Показать последние действия модерации")
@app_commands.describe(limit="Количество записей для показа")
@is_admin_only()
async def slash_mod_logs(interaction: discord.Interaction, limit: int = 10):
    guild_id = str(interaction.guild_id)
    
    if guild_id in settings.mod_logs:
        logs = settings.mod_logs[guild_id][-limit:]
        
        embed = discord.Embed(
            title="📋 Последние действия модерации",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
        
        for log in reversed(logs):
            date = datetime.datetime.fromisoformat(log["date"]).strftime("%d.%m.%Y %H:%M")
            embed.add_field(
                name=f"{log['action']} - {date}",
                value=f"**Модератор:** <@{log['moderator']}> (`{log['moderator']}`)\n**Пользователь:** <@{log['target']}> (`{log['target']}`)\n**Причина:** {log['reason']}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Логи пока отсутствуют", ephemeral=True)

@bot.tree.command(name="help", description="Показать список команд")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 Команды модерационного бота",
        description="**Автор: by Ilya Vetrov**\nГлавный администратор имеет абсолютные права на всех серверах.\n\n**Все команды доступны только администраторам сервера!**",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="⚙️ Настройка ролей",
        value="`/set_join_role` - установить роль для новичков\n`/remove_join_role` - отключить автовыдачу",
        inline=False
    )
    
    embed.add_field(
        name="📋 Настройка каналов для логов",
        value="`/setup_all_logs` - **БЫСТРАЯ НАСТРОЙКА** (все логи в один канал)\n"
              "`/set_mod_log_channel` - канал для действий модерации\n"
              "`/set_message_delete_channel` - удаленные сообщения\n"
              "`/set_message_edit_channel` - измененные сообщения\n"
              "`/set_bulk_delete_channel` - массовые удаления\n"
              "`/set_role_give_channel` - выдача/снятие ролей\n"
              "`/set_warns_channel` - предупреждения\n"
              "`/set_voice_channel` - голосовые каналы\n"
              "`/set_nickname_channel` - смена никнеймов\n"
              "`/show_log_channels` - показать настройки",
        inline=False
    )
    
    embed.add_field(
        name="🛡️ Модерация",
        value="`/kick` - кикнуть пользователя\n`/ban` - забанить пользователя\n`/unban` - разбанить по ID\n`/mute` - замутить на время\n`/unmute` - снять мут\n`/clear` - очистить сообщения\n`/warn` - выдать предупреждение\n`/warns` - показать предупреждения\n`/mod_logs` - показать историю действий",
        inline=False
    )
    
    embed.add_field(
        name="🧪 Тестирование",
        value="`/test_welcome` - протестировать приветственное сообщение\n`/test_role_log` - проверить канал логов ролей",
        inline=False
    )
    
    embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
    await interaction.response.send_message(embed=embed)

# ==================== ПРЕФИКСНЫЕ КОМАНДЫ ====================

@bot.command(name='синхронизировать')
async def sync_command(ctx):
    if ctx.author.id != MAIN_ADMIN_ID and not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Только администраторы!")
        return
    
    await bot.tree.sync()
    await ctx.send("✅ Слэш-команды синхронизированы! by Ilya Vetrov")

@bot.command(name='статус')
async def status_command(ctx):
    if ctx.author.id != MAIN_ADMIN_ID and not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Только администраторы!")
        return
    
    embed = discord.Embed(
        title="🤖 СТАТУС БОТА",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
    )
    
    embed.add_field(name="📱 Имя бота", value=f"```{bot.user.name}```", inline=True)
    embed.add_field(name="🆔 ID", value=f"```{bot.user.id}```", inline=True)
    embed.add_field(name="🌐 Серверов", value=f"```{len(bot.guilds)}```", inline=True)
    
    embed.add_field(name="⚙️ Автовыдача ролей", value=f"```{len(settings.join_roles)} серверов```", inline=True)
    
    total_channels = sum(len(v) for v in settings.log_channels.values())
    embed.add_field(name="📋 Каналов логов", value=f"```{total_channels}```", inline=True)
    
    embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
    
    await ctx.send(embed=embed)

# ==================== ОБРАБОТЧИКИ СОБЫТИЙ ====================

@bot.event
async def on_member_join(member):
    """Приветствие при заходе нового участника (без выдачи роли)"""
    
    # Приветствие только для вашего конкретного сервера
    if member.guild.id == YOUR_GUILD_ID:
        channel = bot.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            welcome_text = (
                "Поздравляю, Ты успешно прошел обзвон. на пост лидера своей фракции.\n"
                "Ниже приведена инструкция:\n\n"
                "Заполняем по форме:\n"
                "**Nick ставим - Фракция | NickName**\n"
                "**Фракция | NickName**\n"
                "**Почта @gmail**\n"
                "**Ссылка на Форумник**\n\n"
                "1. На форуме обязательно поставь никнейм. Как в игре.\n"
                "2. Обязательно включи двухфакторную аутентификацию. в дискорде и игре.\n"
                f"3. По вопросам обращайтесь к своим кураторам. Узнать, кто ваш куратор, можно, посмотрев этот канал. <#{CURATOR_CHANNEL_ID}>.\n"
                f"4. С балловой системе можно ознакомиться в этом канале <#{BALANCE_CHANNEL_ID}>"
            )
            
            embed = discord.Embed(
                title="👋 ДОБРО ПОЖАЛОВАТЬ!",
                description=welcome_text,
                color=discord.Color.green()
            )
            embed.set_footer(text="by Ilya Vetrov")
            await channel.send(f"{member.mention}", embed=embed)
            
            # Отправляем ТО ЖЕ САМОЕ сообщение в личные сообщения
            try:
                dm_embed = discord.Embed(
                    title="👋 ДОБРО ПОЖАЛОВАТЬ НА СЕРВЕР!",
                    description=welcome_text,
                    color=discord.Color.green()
                )
                dm_embed.set_footer(text="by Ilya Vetrov")
                await member.send(embed=dm_embed)
                logger.info(f"📨 Отправлено ЛС пользователю {member.name} ({member.id})")
            except discord.Forbidden:
                logger.warning(f"❌ Не удалось отправить ЛС пользователю {member.name} - закрыты личные сообщения")
            except Exception as e:
                logger.error(f"❌ Ошибка при отправке ЛС: {e}")

@bot.event
async def on_message_delete(message):
    """Логирование удаленных сообщений"""
    if message.author.bot or not message.guild:
        return
    await log_message_delete(message.guild, message)

@bot.event
async def on_message_edit(before, after):
    """Логирование измененных сообщений"""
    if before.author.bot or before.content == after.content or not before.guild:
        return
    
    guild_id = str(before.guild.id)
    if guild_id in settings.log_channels.get("message_edit", {}):
        channel_id = settings.log_channels["message_edit"][guild_id]
        channel = before.guild.get_channel(int(channel_id))
        if channel:
            embed = discord.Embed(
                title="✏ СООБЩЕНИЕ ИЗМЕНЕНО",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.utcnow()
            )
            
            author_text = f"{before.author.mention}\nID: `{before.author.id}`\nИмя: `{before.author.name}`"
            embed.add_field(name="👤 Автор", value=author_text, inline=True)
            
            channel_text = f"{before.channel.mention}\nID: `{before.channel.id}`"
            embed.add_field(name="📌 Канал", value=channel_text, inline=True)
            
            message_link = f"https://discord.com/channels/{before.guild.id}/{before.channel.id}/{before.id}"
            embed.add_field(name="🔗 Ссылка", value=f"[Перейти]({message_link})", inline=True)
            
            old_content = before.content[:500] + "..." if len(before.content) > 500 else before.content
            embed.add_field(name="📤 Было", value=f"```{old_content or '[Пусто]'}```", inline=False)
            
            new_content = after.content[:500] + "..." if len(after.content) > 500 else after.content
            embed.add_field(name="📥 Стало", value=f"```{new_content or '[Пусто]'}```", inline=False)
            
            embed.set_footer(text=f"by Ilya Vetrov • ID сообщения: {before.id}")
            await channel.send(embed=embed)

@bot.event
async def on_bulk_message_delete(messages):
    """Логирование массового удаления сообщений"""
    if not messages:
        return
    
    guild = messages[0].guild
    if not guild:
        return
    
    guild_id = str(guild.id)
    
    if guild_id in settings.log_channels.get("message_delete", {}):
        channel_id = settings.log_channels["message_delete"][guild_id]
        log_channel = guild.get_channel(int(channel_id))
        
        if log_channel:
            info_embed = discord.Embed(
                title="📦 МАССОВОЕ УДАЛЕНИЕ СООБЩЕНИЙ",
                description=f"**Канал:** {messages[0].channel.mention}\n**Количество:** {len(messages)} сообщений",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            info_embed.set_footer(text="by Ilya Vetrov")
            await log_channel.send(embed=info_embed)
            
            for i, message in enumerate(messages[:10]):
                if not message.author.bot:
                    embed = discord.Embed(
                        title=f"🗑 УДАЛЕННОЕ СООБЩЕНИЕ #{i+1}",
                        color=discord.Color.red(),
                        timestamp=datetime.datetime.utcnow()
                    )
                    
                    author_text = f"{message.author.mention}\nID: `{message.author.id}`\nИмя: `{message.author.name}`"
                    embed.add_field(name="👤 Автор", value=author_text, inline=True)
                    
                    if message.created_at:
                        time_text = message.created_at.strftime("%d.%m.%Y %H:%M:%S")
                        embed.add_field(name="⏰ Отправлено", value=f"`{time_text}`", inline=True)
                    
                    if message.content:
                        content = message.content[:500] + "..." if len(message.content) > 500 else message.content
                        embed.add_field(name="📝 Содержание", value=f"```{content}```", inline=False)
                    
                    embed.set_footer(text=f"by Ilya Vetrov • ID: {message.id}")
                    await log_channel.send(embed=embed)
            
            if len(messages) > 10:
                await log_channel.send(f"*... и ещё {len(messages) - 10} сообщений*")

@bot.event
async def on_member_update(before, after):
    """Логирование изменений профиля пользователя (роли и никнеймы)"""
    if before.bot or not before.guild:
        return
    
    guild_id = str(before.guild.id)
    
    # Логирование смены никнейма
    if guild_id in settings.log_channels.get("nickname", {}):
        if before.nick != after.nick:
            old_nick = before.nick or before.name
            new_nick = after.nick or after.name
            
            description = f"📝 {before.mention} (`{before.id}`) **сменил никнейм**\n**Было:** `{old_nick}`\n**Стало:** `{new_nick}`"
            await log_nickname(before.guild, description)
    
    # Логирование изменений ролей
    if guild_id in settings.log_channels.get("role_give", {}):
        before_roles = set(before.roles)
        after_roles = set(after.roles)
        
        # Выданные роли
        added_roles = after_roles - before_roles
        for role in added_roles:
            if role.name != "@everyone":
                description = f"➕ {before.mention} (`{before.id}`) **получил роль** {role.mention}\n**ID роли:** `{role.id}`"
                await log_role_give(before.guild, description, discord.Color.green())
                logger.info(f"Лог роли (выдача): {description}")
        
        # Снятые роли
        removed_roles = before_roles - after_roles
        for role in removed_roles:
            if role.name != "@everyone":
                description = f"➖ {before.mention} (`{before.id}`) **лишился роли** {role.mention}\n**ID роли:** `{role.id}`"
                await log_role_give(before.guild, description, discord.Color.red())
                logger.info(f"Лог роли (снятие): {description}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot or not member.guild:
        return
    
    guild_id = str(member.guild.id)
    if guild_id not in settings.log_channels.get("voice", {}):
        return
    
    if before.channel is None and after.channel is not None:
        description = f"🔊 {member.mention} (`{member.id}`) **зашел** в голосовой канал {after.channel.mention}"
        await log_voice(member.guild, description, discord.Color.green())
    
    elif before.channel is not None and after.channel is None:
        description = f"🔇 {member.mention} (`{member.id}`) **вышел** из голосового канала {before.channel.mention}"
        await log_voice(member.guild, description, discord.Color.red())
    
    elif before.channel != after.channel:
        description = f"🔄 {member.mention} (`{member.id}`) **переместился** из {before.channel.mention} в {after.channel.mention}"
        await log_voice(member.guild, description, discord.Color.blue())

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def save_mod_log(guild, action, moderator, target, reason, duration=None):
    guild_id = str(guild.id)
    
    if guild_id not in settings.mod_logs:
        settings.mod_logs[guild_id] = []
    
    log_entry = {
        "action": action,
        "moderator": moderator.id,
        "target": target.id,
        "reason": reason,
        "date": datetime.datetime.utcnow().isoformat()
    }
    
    if duration:
        log_entry["duration"] = duration
    
    settings.mod_logs[guild_id].append(log_entry)
    
    if len(settings.mod_logs[guild_id]) > 1000:
        settings.mod_logs[guild_id] = settings.mod_logs[guild_id][-1000:]
    
    settings.save_mod_logs()

# ==================== ОБРАБОТКА ОШИБОК ====================

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Ошибка доступа",
            description="У вас нет прав администратора для использования этой команды!",
            color=discord.Color.red()
        )
        embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    elif isinstance(error, app_commands.errors.CheckFailure):
        embed = discord.Embed(
            title="❌ Ошибка доступа",
            description="Только администраторы могут использовать эту команду!",
            color=discord.Color.red()
        )
        embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(
            title="❌ Произошла ошибка",
            description=str(error),
            color=discord.Color.red()
        )
        embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.error(f"Ошибка команды: {error}")

# ==================== ЗАПУСК БОТА ====================

if __name__ == "__main__":
    print("🔄 Загрузка данных...")
    settings.load_all()
    
    token = os.getenv('TOKEN')
    
    if not token:
        print("❌ ОШИБКА: Токен не найден в переменных окружения!")
        print("📝 Убедитесь что в BotHost добавлена переменная TOKEN с вашим токеном")
        exit(1)
    
    print("🔄 Запуск бота...")
    try:
        bot.run(token)
    except discord.LoginFailure:
        print("❌ ОШИБКА: Неправильный токен бота!")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
