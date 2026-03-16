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

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.moderation = True

class ModerationBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.initial_extensions = []
        
    async def setup_hook(self):
        # Синхронизация слеш-команд
        await self.tree.sync()
        logger.info("✅ Слеш-команды синхронизированы")
        
    async def on_ready(self):
        # Информационная панель при запуске (by Ilya Vetrov)
        print("\n" + "="*50)
        print("🤖 МОДЕРАЦИОННЫЙ БОТ ЗАПУЩЕН")
        print("="*50)
        print(f"📱 Имя бота: {self.user.name}")
        print(f"🆔 ID бота: {self.user.id}")
        print(f"🌐 Серверов: {len(self.guilds)}")
        print(f"👑 Главный администратор: {MAIN_ADMIN_ID}")
        print(f"👨‍💻 Автор: Ilya Vetrov")
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
        """Создает папку для данных, если её нет"""
        if not os.path.exists(self.data_folder):
            os.makedirs(self.data_folder)
            logger.info(f"📁 Создана папка {self.data_folder}")
    
    def save_data(self, filename, local_filename, data):
        """Сохранение данных в JSON"""
        try:
            # Сохраняем в защищенную папку
            filepath = os.path.join(self.data_folder, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            # Дублируем в корень
            with open(local_filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                
            logger.info(f"💾 Данные сохранены в {filename}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения {filename}: {e}")
            return False
    
    def load_data(self, filename, local_filename, default=None):
        """Загрузка данных из JSON"""
        # Сначала пробуем загрузить из защищенной папки
        filepath = os.path.join(self.data_folder, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки {filename}: {e}")
        
        # Если нет, пробуем загрузить из корня
        if os.path.exists(local_filename):
            try:
                with open(local_filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Сразу сохраняем в защищенную папку
                self.save_data(filename, local_filename, data)
                return data
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки {local_filename}: {e}")
        
        return default if default is not None else {}

data_manager = DataManager()

# ==================== КЛАССЫ ДЛЯ ХРАНЕНИЯ ДАННЫХ ====================

class GuildSettings:
    def __init__(self):
        self.join_roles = {}  # guild_id: role_id
        self.log_channels = {}  # guild_id: channel_id
        self.mod_logs = {}  # guild_id: [logs]
        self.warns = {}  # guild_id: {user_id: [warns]}
        
    def load_all(self):
        """Загружает все настройки"""
        self.join_roles = data_manager.load_data('join_roles.json', LOCAL_JOIN_ROLES, {})
        self.log_channels = data_manager.load_data('log_channels.json', LOCAL_LOG_CHANNELS, {})
        self.mod_logs = data_manager.load_data('mod_logs.json', LOCAL_MOD_LOGS, {})
        self.warns = data_manager.load_data('warns.json', LOCAL_WARNS, {})
        
        # Конвертируем ключи в int где необходимо
        self.join_roles = {int(k) if isinstance(k, str) and k.isdigit() else k: v for k, v in self.join_roles.items()}
        self.log_channels = {int(k) if isinstance(k, str) and k.isdigit() else k: v for k, v in self.log_channels.items()}
        self.mod_logs = {int(k) if isinstance(k, str) and k.isdigit() else k: v for k, v in self.mod_logs.items()}
        self.warns = {int(k) if isinstance(k, str) and k.isdigit() else k: v for k, v in self.warns.items()}
        
        logger.info(f"📂 Загружено: join_roles: {len(self.join_roles)}, log_channels: {len(self.log_channels)}")
        
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

def is_admin():
    """Проверка, является ли пользователь администратором или главным админом"""
    async def predicate(interaction: discord.Interaction):
        # Главный администратор имеет абсолютные права
        if interaction.user.id == MAIN_ADMIN_ID:
            return True
        # Обычная проверка на админа
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

# ==================== СЛЕШ-КОМАНДЫ ====================

@bot.tree.command(name="set_join_role", description="Установить роль для новых участников")
@app_commands.describe(role="Роль, которая будет выдаваться новым участникам")
@is_admin()
async def slash_set_join_role(interaction: discord.Interaction, role: discord.Role):
    settings.join_roles[str(interaction.guild_id)] = role.id
    settings.save_join_roles()
    
    embed = discord.Embed(
        title="✅ Роль установлена",
        description=f"Новые участники теперь будут получать роль {role.mention}",
        color=discord.Color.green()
    )
    embed.set_footer(text="Ilya Vetrov • Модерационный бот")
    await interaction.response.send_message(embed=embed)
    await log_action(interaction.guild, f"⚙️ {interaction.user.mention} установил роль {role.mention} для новичков")

@bot.tree.command(name="remove_join_role", description="Отключить автоматическую выдачу роли")
@is_admin()
async def slash_remove_join_role(interaction: discord.Interaction):
    if str(interaction.guild_id) in settings.join_roles:
        del settings.join_roles[str(interaction.guild_id)]
        settings.save_join_roles()
        
        embed = discord.Embed(
            title="✅ Автовыдача отключена",
            description="Новые участники больше не будут получать роль автоматически",
            color=discord.Color.green()
        )
        embed.set_footer(text="Ilya Vetrov • Модерационный бот")
        await interaction.response.send_message(embed=embed)
        await log_action(interaction.guild, f"⚙️ {interaction.user.mention} отключил автовыдачу роли")
    else:
        await interaction.response.send_message("❌ Автовыдача роли не была настроена", ephemeral=True)

@bot.tree.command(name="kick", description="Кикнуть пользователя")
@app_commands.describe(member="Пользователь для кика", reason="Причина кика")
@is_admin()
async def slash_kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    try:
        await member.kick(reason=reason)
        
        embed = discord.Embed(
            title="👢 Пользователь кикнут",
            description=f"**Пользователь:** {member.mention}\n**Причина:** {reason}",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Модератор: {interaction.user} • Ilya Vetrov")
        await interaction.response.send_message(embed=embed)
        
        await log_action(interaction.guild, f"👢 {interaction.user.mention} кикнул {member.mention}\nПричина: {reason}")
        await save_mod_log(interaction.guild, "kick", interaction.user, member, reason)
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="ban", description="Забанить пользователя")
@app_commands.describe(member="Пользователь для бана", reason="Причина бана")
@is_admin()
async def slash_ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    try:
        await member.ban(reason=reason, delete_message_days=0)
        
        embed = discord.Embed(
            title="🔨 Пользователь забанен",
            description=f"**Пользователь:** {member.mention}\n**Причина:** {reason}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Модератор: {interaction.user} • Ilya Vetrov")
        await interaction.response.send_message(embed=embed)
        
        await log_action(interaction.guild, f"🔨 {interaction.user.mention} забанил {member.mention}\nПричина: {reason}")
        await save_mod_log(interaction.guild, "ban", interaction.user, member, reason)
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="unban", description="Разбанить пользователя по ID")
@app_commands.describe(user_id="ID пользователя", reason="Причина разбана")
@is_admin()
async def slash_unban(interaction: discord.Interaction, user_id: str, reason: str = "Не указана"):
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=reason)
        
        embed = discord.Embed(
            title="🔓 Пользователь разбанен",
            description=f"**Пользователь:** {user.name}\n**Причина:** {reason}",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Модератор: {interaction.user} • Ilya Vetrov")
        await interaction.response.send_message(embed=embed)
        
        await log_action(interaction.guild, f"🔓 {interaction.user.mention} разбанил {user.name}\nПричина: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="mute", description="Замутить пользователя")
@app_commands.describe(member="Пользователь для мута", minutes="Длительность в минутах", reason="Причина мута")
@is_admin()
async def slash_mute(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Не указана"):
    try:
        duration = datetime.timedelta(minutes=minutes)
        await member.timeout(duration, reason=reason)
        
        embed = discord.Embed(
            title="🔇 Пользователь замучен",
            description=f"**Пользователь:** {member.mention}\n**Длительность:** {minutes} мин\n**Причина:** {reason}",
            color=discord.Color.dark_gray(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Модератор: {interaction.user} • Ilya Vetrov")
        await interaction.response.send_message(embed=embed)
        
        await log_action(interaction.guild, f"🔇 {interaction.user.mention} замутил {member.mention} на {minutes} мин\nПричина: {reason}")
        await save_mod_log(interaction.guild, "mute", interaction.user, member, reason, minutes)
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="Снять мут с пользователя")
@app_commands.describe(member="Пользователь для снятия мута", reason="Причина")
@is_admin()
async def slash_unmute(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    try:
        await member.timeout(None, reason=reason)
        
        embed = discord.Embed(
            title="🔊 Мут снят",
            description=f"**Пользователь:** {member.mention}\n**Причина:** {reason}",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Модератор: {interaction.user} • Ilya Vetrov")
        await interaction.response.send_message(embed=embed)
        
        await log_action(interaction.guild, f"🔊 {interaction.user.mention} снял мут с {member.mention}\nПричина: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="clear", description="Очистить сообщения в канале")
@app_commands.describe(amount="Количество сообщений для удаления")
@is_admin()
async def slash_clear(interaction: discord.Interaction, amount: int):
    try:
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        
        embed = discord.Embed(
            title="🧹 Сообщения удалены",
            description=f"Удалено **{len(deleted)}** сообщений",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Ilya Vetrov • Модерационный бот")
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        await log_action(interaction.guild, f"🧹 {interaction.user.mention} очистил {len(deleted)} сообщений в {interaction.channel.mention}")
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="warn", description="Выдать предупреждение пользователю")
@app_commands.describe(member="Пользователь", reason="Причина предупреждения")
@is_admin()
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
        description=f"**Пользователь:** {member.mention}\n**Предупреждений:** {len(settings.warns[guild_id][user_id])}\n**Причина:** {reason}",
        color=discord.Color.yellow(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text=f"Модератор: {interaction.user} • Ilya Vetrov")
    await interaction.response.send_message(embed=embed)
    
    try:
        await member.send(f"Вы получили предупреждение на сервере **{interaction.guild.name}**\n**Причина:** {reason}")
    except:
        pass
    
    await log_action(interaction.guild, f"⚠️ {interaction.user.mention} выдал предупреждение {member.mention}\nПричина: {reason}")

@bot.tree.command(name="warns", description="Показать предупреждения пользователя")
@app_commands.describe(member="Пользователь")
async def slash_warns(interaction: discord.Interaction, member: discord.Member):
    guild_id = str(interaction.guild_id)
    
    if guild_id in settings.warns and str(member.id) in settings.warns[guild_id]:
        warns = settings.warns[guild_id][str(member.id)]
        
        embed = discord.Embed(
            title=f"Предупреждения: {member.display_name}",
            color=discord.Color.orange()
        )
        embed.set_footer(text="Ilya Vetrov • Модерационный бот")
        
        for i, warn in enumerate(warns[-10:], 1):  # Показываем последние 10
            mod = bot.get_user(warn["moderator"])
            mod_name = mod.name if mod else f"ID: {warn['moderator']}"
            date = datetime.datetime.fromisoformat(warn["date"]).strftime("%d.%m.%Y %H:%M")
            embed.add_field(
                name=f"#{i} - {date}",
                value=f"**Модератор:** {mod_name}\n**Причина:** {warn['reason']}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(f"У пользователя {member.mention} нет предупреждений", ephemeral=True)

@bot.tree.command(name="set_log_channel", description="Установить канал для логов")
@app_commands.describe(channel="Канал для логирования")
@is_admin()
async def slash_set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    settings.log_channels[str(interaction.guild_id)] = channel.id
    settings.save_log_channels()
    
    embed = discord.Embed(
        title="✅ Канал логов установлен",
        description=f"Все действия будут логироваться в {channel.mention}",
        color=discord.Color.green()
    )
    embed.set_footer(text="Ilya Vetrov • Модерационный бот")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="mod_logs", description="Показать последние действия модерации")
@app_commands.describe(limit="Количество записей для показа")
@is_admin()
async def slash_mod_logs(interaction: discord.Interaction, limit: int = 10):
    guild_id = str(interaction.guild_id)
    
    if guild_id in settings.mod_logs:
        logs = settings.mod_logs[guild_id][-limit:]
        
        embed = discord.Embed(
            title="📋 Последние действия модерации",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="Ilya Vetrov • Модерационный бот")
        
        for log in reversed(logs):
            date = datetime.datetime.fromisoformat(log["date"]).strftime("%d.%m.%Y %H:%M")
            embed.add_field(
                name=f"{log['action']} - {date}",
                value=f"**Модератор:** <@{log['moderator']}>\n**Пользователь:** <@{log['target']}>\n**Причина:** {log['reason']}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Логи пока отсутствуют", ephemeral=True)

@bot.tree.command(name="help", description="Показать список команд")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 Команды модерационного бота",
        description="**Автор: Ilya Vetrov**\nГлавный администратор имеет абсолютные права на всех серверах.",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="⚙️ Настройка ролей",
        value="`/set_join_role` - установить роль для новичков\n`/remove_join_role` - отключить автовыдачу",
        inline=False
    )
    
    embed.add_field(
        name="🛡️ Модерация",
        value="`/kick` - кикнуть пользователя\n`/ban` - забанить пользователя\n`/unban` - разбанить по ID\n`/mute` - замутить на время\n`/unmute` - снять мут\n`/clear` - очистить сообщения\n`/warn` - выдать предупреждение\n`/warns` - показать предупреждения",
        inline=False
    )
    
    embed.add_field(
        name="📋 Логирование",
        value="`/set_log_channel` - установить канал для логов\n`/mod_logs` - показать историю действий",
        inline=False
    )
    
    embed.set_footer(text="Ilya Vetrov • Модерационный бот")
    await interaction.response.send_message(embed=embed)

# ==================== ПРЕФИКСНЫЕ КОМАНДЫ ====================

@bot.command(name='синхронизировать')
async def sync_command(ctx):
    if ctx.author.id != MAIN_ADMIN_ID and not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Только администраторы!")
        return
    
    await bot.tree.sync()
    await ctx.send("✅ Слэш-команды синхронизированы!")

@bot.command(name='статус')
async def status_command(ctx):
    """Показать статус бота"""
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
    
    # Статистика настроек
    embed.add_field(name="⚙️ Автовыдача ролей", value=f"```{len(settings.join_roles)} серверов```", inline=True)
    embed.add_field(name="📋 Каналов логов", value=f"```{len(settings.log_channels)}```", inline=True)
    
    embed.set_footer(text="Ilya Vetrov • Модерационный бот")
    
    await ctx.send(embed=embed)

# ==================== ОБРАБОТЧИКИ СОБЫТИЙ ====================

@bot.event
async def on_member_join(member):
    """Выдача роли при заходе нового участника"""
    guild_id = str(member.guild.id)
    if guild_id in settings.join_roles:
        role_id = settings.join_roles[guild_id]
        role = member.guild.get_role(int(role_id))
        if role:
            await member.add_roles(role)
            logger.info(f'Выдана роль {role.name} пользователю {member.name}')
            await log_action(member.guild, f'✅ Пользователь {member.mention} получил роль {role.mention}')

@bot.event
async def on_message_delete(message):
    """Логирование удаленных сообщений"""
    if message.author.bot or not message.guild:
        return
    
    guild_id = str(message.guild.id)
    if guild_id in settings.log_channels:
        channel = message.guild.get_channel(int(settings.log_channels[guild_id]))
        if channel:
            embed = discord.Embed(
                title="🗑 Сообщение удалено",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="Автор", value=message.author.mention, inline=True)
            embed.add_field(name="Канал", value=message.channel.mention, inline=True)
            
            if message.content:
                embed.add_field(name="Содержание", value=message.content[:1000], inline=False)
            
            if message.attachments:
                files = "\n".join([f"[{f.filename}]({f.url})" for f in message.attachments])
                embed.add_field(name="Вложения", value=files[:1000], inline=False)
            
            embed.set_footer(text="Ilya Vetrov • Логирование сообщений")
            await channel.send(embed=embed)

@bot.event
async def on_message_edit(before, after):
    """Логирование измененных сообщений"""
    if before.author.bot or before.content == after.content or not before.guild:
        return
    
    guild_id = str(before.guild.id)
    if guild_id in settings.log_channels:
        channel = before.guild.get_channel(int(settings.log_channels[guild_id]))
        if channel:
            embed = discord.Embed(
                title="✏ Сообщение изменено",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="Автор", value=before.author.mention, inline=True)
            embed.add_field(name="Канал", value=before.channel.mention, inline=True)
            embed.add_field(name="До", value=before.content[:500] or "[Пусто]", inline=False)
            embed.add_field(name="После", value=after.content[:500] or "[Пусто]", inline=False)
            
            embed.set_footer(text="Ilya Vetrov • Логирование сообщений")
            await channel.send(embed=embed)

@bot.event
async def on_bulk_message_delete(messages):
    """Логирование массового удаления сообщений"""
    if not messages:
        return
        
    guild = messages[0].guild
    if guild and str(guild.id) in settings.log_channels:
        channel = guild.get_channel(int(settings.log_channels[str(guild.id)]))
        if channel:
            embed = discord.Embed(
                title="🗑 Массовое удаление сообщений",
                description=f"**Канал:** {messages[0].channel.mention}\n**Количество:** {len(messages)}",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text="Ilya Vetrov • Логирование сообщений")
            await channel.send(embed=embed)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def log_action(guild, action_description):
    """Логирование действий в канал"""
    guild_id = str(guild.id)
    if guild_id in settings.log_channels:
        channel = guild.get_channel(int(settings.log_channels[guild_id]))
        if channel:
            embed = discord.Embed(
                description=action_description,
                color=discord.Color.blue(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text="Ilya Vetrov • Логирование действий")
            await channel.send(embed=embed)

async def save_mod_log(guild, action, moderator, target, reason, duration=None):
    """Сохранение действий модерации"""
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
    
    # Ограничиваем количество логов до 1000 на сервер
    if len(settings.mod_logs[guild_id]) > 1000:
        settings.mod_logs[guild_id] = settings.mod_logs[guild_id][-1000:]
    
    settings.save_mod_logs()

# ==================== ОБРАБОТКА ОШИБОК ====================

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        embed = discord.Embed(
            title="❌ Ошибка доступа",
            description="У вас нет прав для использования этой команды!",
            color=discord.Color.red()
        )
        embed.set_footer(text="Ilya Vetrov • Модерационный бот")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    elif isinstance(error, app_commands.errors.CheckFailure):
        embed = discord.Embed(
            title="❌ Ошибка доступа",
            description="Только администраторы могут использовать эту команду!",
            color=discord.Color.red()
        )
        embed.set_footer(text="Ilya Vetrov • Модерационный бот")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(
            title="❌ Произошла ошибка",
            description=str(error),
            color=discord.Color.red()
        )
        embed.set_footer(text="Ilya Vetrov • Модерационный бот")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.error(f"Ошибка команды: {error}")

# ==================== ЗАПУСК БОТА ====================

if __name__ == "__main__":
    # Загружаем настройки
    print("🔄 Загрузка данных...")
    settings.load_all()
    
    # Получаем токен из переменной окружения (как настроено в BotHost)
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
