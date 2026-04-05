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
from threading import Lock

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ID главных администраторов (ТОЛЬКО ОНИ МОГУТ ИСПОЛЬЗОВАТЬ ВСЕ КОМАНДЫ)
MAIN_ADMIN_IDS = [927642459998138418, 500965898476322817]

# ID вашего сервера и каналов
YOUR_GUILD_ID = 886219875452854292
WELCOME_CHANNEL_ID = 886221288421589004
CURATOR_CHANNEL_ID = 1178309021065809951
BALANCE_CHANNEL_ID = 1444397866499182665
LEADERS_CHANNEL_ID = 904495052330508308      # Канал для списка лидеров

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.moderation = True
intents.voice_states = True

# ==================== СИСТЕМА ХРАНЕНИЯ ДАННЫХ ====================

class PersistentDataManager:
    def __init__(self):
        self.data_folder = '/app/data'
        self.backup_folder = os.path.join(self.data_folder, 'backups')
        self._lock = Lock()
        self.ensure_folders()
        self.settings = self.load_settings()
        
    def ensure_folders(self):
        os.makedirs(self.data_folder, exist_ok=True)
        os.makedirs(self.backup_folder, exist_ok=True)
        logger.info(f"📁 Папки данных: {self.data_folder}")
        
    def load_settings(self):
        settings_file = os.path.join(self.data_folder, 'bot_settings.json')
        
        default_settings = {
            "version": "2.0",
            "last_updated": datetime.datetime.utcnow().isoformat(),
            "join_roles": {},
            "log_channels": {
                "mod_actions": {},
                "message_delete": {},
                "message_edit": {},
                "bulk_delete": {},
                "role_give": {},
                "warns": {},
                "voice": {},
                "nickname": {}
            },
            "mod_logs": {},
            "warns": {},
            "embed_templates": {}
        }
        
        try:
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    for key in ['join_roles', 'mod_logs', 'warns']:
                        if key in loaded:
                            loaded[key] = {int(k) if k.isdigit() else k: v for k, v in loaded[key].items()}
                    
                    if 'log_channels' in loaded:
                        for log_type in loaded['log_channels']:
                            loaded['log_channels'][log_type] = {
                                int(k) if k.isdigit() else k: v 
                                for k, v in loaded['log_channels'][log_type].items()
                            }
                    
                    logger.info(f"✅ Загружены настройки")
                    return loaded
            else:
                self.save_settings(default_settings)
                return default_settings
        except Exception as e:
            logger.error(f"Ошибка загрузки: {e}")
            return default_settings
    
    def save_settings(self, settings=None):
        with self._lock:
            if settings is None:
                settings = self.settings
            
            settings["last_updated"] = datetime.datetime.utcnow().isoformat()
            settings_file = os.path.join(self.data_folder, 'bot_settings.json')
            
            if os.path.exists(settings_file):
                backup_file = os.path.join(self.backup_folder, f"backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                try:
                    import shutil
                    shutil.copy2(settings_file, backup_file)
                except:
                    pass
            
            try:
                save_data = self._prepare_for_json(settings)
                with open(settings_file, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, ensure_ascii=False, indent=4)
                return True
            except Exception as e:
                logger.error(f"Ошибка сохранения: {e}")
                return False
    
    def _prepare_for_json(self, data):
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                new_key = str(k) if isinstance(k, int) else k
                result[new_key] = self._prepare_for_json(v)
            return result
        elif isinstance(data, list):
            return [self._prepare_for_json(item) for item in data]
        else:
            return data
    
    def get_join_role(self, guild_id):
        return self.settings["join_roles"].get(guild_id)
    
    def set_join_role(self, guild_id, role_id):
        self.settings["join_roles"][guild_id] = role_id
        self.save_settings()
    
    def remove_join_role(self, guild_id):
        if guild_id in self.settings["join_roles"]:
            del self.settings["join_roles"][guild_id]
            self.save_settings()
            return True
        return False
    
    def get_log_channel(self, guild_id, log_type):
        return self.settings["log_channels"].get(log_type, {}).get(guild_id)
    
    def set_log_channel(self, guild_id, log_type, channel_id):
        if log_type not in self.settings["log_channels"]:
            self.settings["log_channels"][log_type] = {}
        self.settings["log_channels"][log_type][guild_id] = channel_id
        self.save_settings()
    
    def get_warns(self, guild_id, user_id=None):
        guild_warns = self.settings["warns"].get(guild_id, {})
        if user_id:
            return guild_warns.get(str(user_id), [])
        return guild_warns
    
    def add_warn(self, guild_id, user_id, warn_data):
        if guild_id not in self.settings["warns"]:
            self.settings["warns"][guild_id] = {}
        
        user_key = str(user_id)
        if user_key not in self.settings["warns"][guild_id]:
            self.settings["warns"][guild_id][user_key] = []
        
        self.settings["warns"][guild_id][user_key].append(warn_data)
        self.save_settings()
    
    def get_mod_logs(self, guild_id):
        return self.settings["mod_logs"].get(guild_id, [])
    
    def add_mod_log(self, guild_id, log_entry):
        if guild_id not in self.settings["mod_logs"]:
            self.settings["mod_logs"][guild_id] = []
        
        self.settings["mod_logs"][guild_id].append(log_entry)
        
        if len(self.settings["mod_logs"][guild_id]) > 1000:
            self.settings["mod_logs"][guild_id] = self.settings["mod_logs"][guild_id][-1000:]
        
        self.save_settings()
    
    def save_embed_template(self, guild_id, name, template):
        if str(guild_id) not in self.settings["embed_templates"]:
            self.settings["embed_templates"][str(guild_id)] = {}
        self.settings["embed_templates"][str(guild_id)][name] = template
        self.save_settings()
    
    def get_embed_template(self, guild_id, name):
        return self.settings["embed_templates"].get(str(guild_id), {}).get(name)
    
    def get_all_templates(self, guild_id):
        return self.settings["embed_templates"].get(str(guild_id), {})
    
    def delete_embed_template(self, guild_id, name):
        if str(guild_id) in self.settings["embed_templates"]:
            if name in self.settings["embed_templates"][str(guild_id)]:
                del self.settings["embed_templates"][str(guild_id)][name]
                self.save_settings()
                return True
        return False

data_manager = PersistentDataManager()

# ==================== БОТ ====================

class ModerationBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.start_time = datetime.datetime.utcnow()
        self.leaders_messages = {}  # Словарь для хранения ID сообщений лидеров
        
    async def setup_hook(self):
        await self.tree.sync()
        logger.info("✅ Слеш-команды синхронизированы")
        
    async def on_ready(self):
        print("\n" + "="*60)
        print("🤖 МОДЕРАЦИОННЫЙ БОТ ЗАПУЩЕН")
        print("="*60)
        print(f"📱 Имя бота: {self.user.name}")
        print(f"🆔 ID бота: {self.user.id}")
        print(f"🌐 Серверов: {len(self.guilds)}")
        print(f"👑 Главные администраторы: {MAIN_ADMIN_IDS}")
        print(f"👨‍💻 Автор: by Ilya Vetrov")
        print(f"📅 Время запуска: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
        print("="*60)
        
        total_log_channels = sum(len(channels) for channels in data_manager.settings["log_channels"].values())
        total_join_roles = len(data_manager.settings["join_roles"])
        
        print(f"\n📊 Статистика настроек:")
        print(f"   • Настроено каналов логов: {total_log_channels}")
        print(f"   • Серверов с автовыдачей: {total_join_roles}")
        print()
        
        await self.change_presence(activity=discord.Game(name="/help | Модерация by Ilya Vetrov"))

bot = ModerationBot()

# ==================== ПРОВЕРКА ПРАВ (ТОЛЬКО ДЛЯ УКАЗАННЫХ ID) ====================

def is_allowed_only():
    """Проверка, что пользователь имеет ID из списка MAIN_ADMIN_IDS"""
    async def predicate(interaction: discord.Interaction):
        if interaction.user.id in MAIN_ADMIN_IDS:
            return True
        raise app_commands.errors.MissingPermissions(["Только указанные администраторы могут использовать эту команду!"])
    return app_commands.check(predicate)

# ==================== ФУНКЦИИ ДЛЯ ЛОГОВ ====================

async def send_to_log_channel(guild, log_type, embed):
    if not guild:
        return
    channel_id = data_manager.get_log_channel(guild.id, log_type)
    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.send(embed=embed)
                logger.info(f"📤 Отправлен лог в канал {channel.name} (тип: {log_type})")
            except Exception as e:
                logger.error(f"Ошибка отправки: {e}")

async def log_mod_action(guild, action_description, color=discord.Color.blue()):
    embed = discord.Embed(description=action_description, color=color, timestamp=datetime.datetime.utcnow())
    embed.set_footer(text="by Ilya Vetrov • Модерация")
    await send_to_log_channel(guild, "mod_actions", embed)

async def log_role_give(guild, action_description, color=discord.Color.green()):
    embed = discord.Embed(description=action_description, color=color, timestamp=datetime.datetime.utcnow())
    embed.set_footer(text="by Ilya Vetrov • Изменение ролей")
    await send_to_log_channel(guild, "role_give", embed)

async def log_warn(guild, action_description):
    embed = discord.Embed(description=action_description, color=discord.Color.yellow(), timestamp=datetime.datetime.utcnow())
    embed.set_footer(text="by Ilya Vetrov • Предупреждения")
    await send_to_log_channel(guild, "warns", embed)

async def log_voice(guild, action_description, color=discord.Color.purple()):
    embed = discord.Embed(description=action_description, color=color, timestamp=datetime.datetime.utcnow())
    embed.set_footer(text="by Ilya Vetrov • Голосовые каналы")
    await send_to_log_channel(guild, "voice", embed)

async def log_nickname(guild, action_description):
    embed = discord.Embed(description=action_description, color=discord.Color.teal(), timestamp=datetime.datetime.utcnow())
    embed.set_footer(text="by Ilya Vetrov • Смена ника")
    await send_to_log_channel(guild, "nickname", embed)

async def log_message_delete(guild, message):
    if not guild:
        return
    
    channel_id = data_manager.get_log_channel(guild.id, "message_delete")
    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel:
            embed = discord.Embed(title="🗑 СООБЩЕНИЕ УДАЛЕНО", color=discord.Color.red(), timestamp=datetime.datetime.utcnow())
            
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
            
            if message.mentions:
                mentions_list = [f"{m.mention} (`{m.id}`)" for m in message.mentions[:5]]
                mentions_text = ", ".join(mentions_list)
                if len(message.mentions) > 5:
                    mentions_text += f" и ещё {len(message.mentions)-5}"
                embed.add_field(name="👥 Упоминания", value=mentions_text[:500], inline=False)
            
            embed.set_footer(text=f"by Ilya Vetrov • ID сообщения: {message.id}")
            await channel.send(embed=embed)

async def log_message_edit(before, after):
    """Логирование измененных сообщений"""
    if before.author.bot or before.content == after.content or not before.guild:
        return
    
    channel_id = data_manager.get_log_channel(before.guild.id, "message_edit")
    if channel_id:
        channel = before.guild.get_channel(channel_id)
        if channel:
            embed = discord.Embed(title="✏ СООБЩЕНИЕ ИЗМЕНЕНО", color=discord.Color.orange(), timestamp=datetime.datetime.utcnow())
            
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

async def log_bulk_delete(messages):
    """Логирование массового удаления сообщений - показывает каждое сообщение отдельно"""
    if not messages:
        return
    
    guild = messages[0].guild
    if not guild:
        return
    
    # Сначала пробуем канал для массовых удалений, если нет - то обычный канал удаленных
    channel_id = data_manager.get_log_channel(guild.id, "bulk_delete")
    if not channel_id:
        channel_id = data_manager.get_log_channel(guild.id, "message_delete")
    
    if channel_id:
        log_channel = guild.get_channel(channel_id)
        if log_channel:
            # Информационное сообщение о массовом удалении
            info_embed = discord.Embed(
                title="📦 МАССОВОЕ УДАЛЕНИЕ СООБЩЕНИЙ",
                description=f"**Канал:** {messages[0].channel.mention}\n**Количество:** {len(messages)} сообщений",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            info_embed.set_footer(text="by Ilya Vetrov")
            await log_channel.send(embed=info_embed)
            
            # Отправляем каждое удаленное сообщение отдельно (не больше 15)
            sent_count = 0
            for i, message in enumerate(messages):
                if message.author.bot:
                    continue
                    
                if sent_count >= 15:
                    remaining = len(messages) - sent_count
                    await log_channel.send(f"*... и ещё {remaining} сообщений (показаны первые 15)*")
                    break
                
                embed = discord.Embed(
                    title=f"🗑 УДАЛЕННОЕ СООБЩЕНИЕ #{i+1}",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.utcnow()
                )
                
                author_name = message.author.name
                if message.author.nick:
                    author_name = f"{message.author.nick} ({message.author.name})"
                
                author_text = f"{message.author.mention}\n**Имя:** `{author_name}`\n**ID:** `{message.author.id}`"
                embed.add_field(name="👤 Автор", value=author_text, inline=True)
                embed.add_field(name="📌 Канал", value=f"{message.channel.mention}\nID: `{message.channel.id}`", inline=True)
                
                if message.created_at:
                    time_text = message.created_at.strftime("%d.%m.%Y %H:%M:%S")
                    embed.add_field(name="⏰ Отправлено", value=f"`{time_text}`", inline=True)
                
                if message.content:
                    content = message.content[:800] + "..." if len(message.content) > 800 else message.content
                    embed.add_field(name="📝 Содержание", value=f"```{content}```", inline=False)
                else:
                    embed.add_field(name="📝 Содержание", value="`[Пустое сообщение]`", inline=False)
                
                if message.attachments:
                    attachments_list = []
                    for att in message.attachments:
                        attachments_list.append(f"[{att.filename}]({att.url})")
                    attachments_text = "\n".join(attachments_list)
                    embed.add_field(name="📎 Вложения", value=attachments_text[:500], inline=False)
                
                if message.mentions:
                    mentions_list = [f"{m.mention}" for m in message.mentions[:3]]
                    mentions_text = ", ".join(mentions_list)
                    if len(message.mentions) > 3:
                        mentions_text += f" и ещё {len(message.mentions)-3}"
                    embed.add_field(name="👥 Упоминания", value=mentions_text, inline=False)
                
                embed.set_footer(text=f"by Ilya Vetrov • ID сообщения: {message.id}")
                await log_channel.send(embed=embed)
                sent_count += 1
                await asyncio.sleep(0.3)
            
            if sent_count == 0 and len(messages) > 0:
                await log_channel.send(f"*Все {len(messages)} удаленных сообщений были от ботов*")

async def get_role_moderator(guild, target, role, action_type):
    """Получает информацию о том, кто выдал/снял роль из аудит-лога"""
    try:
        await asyncio.sleep(0.5)
        
        async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.member_role_update):
            if entry.target.id == target.id:
                if action_type == "add" and role in entry.after.roles and role not in entry.before.roles:
                    moderator = entry.user
                    return f"**Выдал:** {moderator.mention} (`{moderator.id}`)"
                elif action_type == "remove" and role in entry.before.roles and role not in entry.after.roles:
                    moderator = entry.user
                    return f"**Снял:** {moderator.mention} (`{moderator.id}`)"
        
        return f"**Инициатор:** `Система/Бот (не удалось определить)`"
        
    except discord.Forbidden:
        return f"**Инициатор:** `Не удалось определить (нет прав на аудит-лог)`"
    except Exception as e:
        return f"**Инициатор:** `Не удалось определить ({str(e)})`"

# ==================== КОМАНДЫ ДЛЯ НАСТРОЙКИ ЛОГОВ ====================

@bot.tree.command(name="setup_all_logs", description="Быстрая настройка всех каналов для логов")
@app_commands.describe(channel="Канал для всех логов")
@is_allowed_only()
async def setup_all_logs(interaction: discord.Interaction, channel: discord.TextChannel):
    for log_type in data_manager.settings["log_channels"].keys():
        data_manager.set_log_channel(interaction.guild_id, log_type, channel.id)
    
    embed = discord.Embed(
        title="✅ ВСЕ КАНАЛЫ ЛОГОВ НАСТРОЕНЫ",
        description=f"Все логи будут отправляться в {channel.mention}\n\n"
                    f"**Настроенные типы логов:**\n"
                    f"• 🛡️ Действия модерации\n"
                    f"• 🗑️ Удаленные сообщения\n"
                    f"• ✏️ Измененные сообщения\n"
                    f"• 📦 Массовые удаления\n"
                    f"• 👥 Выдача/снятие ролей (с указанием кто выдал)\n"
                    f"• ⚠️ Предупреждения\n"
                    f"• 🔊 Голосовые каналы\n"
                    f"• 📝 Смена никнеймов",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_mod_log_channel", description="Установить канал для логов действий модерации")
@app_commands.describe(channel="Канал для логирования")
@is_allowed_only()
async def set_mod_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "mod_actions", channel.id)
    embed = discord.Embed(title="✅ Канал установлен", description=f"Логи модерации в {channel.mention}", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_message_delete_channel", description="Установить канал для логов удаленных сообщений")
@app_commands.describe(channel="Канал для логирования")
@is_allowed_only()
async def set_message_delete_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "message_delete", channel.id)
    embed = discord.Embed(title="✅ Канал установлен", description=f"Логи удаленных сообщений в {channel.mention}", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_message_edit_channel", description="Установить канал для логов измененных сообщений")
@app_commands.describe(channel="Канал для логирования")
@is_allowed_only()
async def set_message_edit_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "message_edit", channel.id)
    embed = discord.Embed(title="✅ Канал установлен", description=f"Логи измененных сообщений в {channel.mention}", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_bulk_delete_channel", description="Установить канал для логов массовых удалений")
@app_commands.describe(channel="Канал для логирования")
@is_allowed_only()
async def set_bulk_delete_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "bulk_delete", channel.id)
    embed = discord.Embed(
        title="✅ Канал установлен", 
        description=f"Логи массовых удалений в {channel.mention}\n\n⚠️ Каждое удаленное сообщение будет показано отдельно!", 
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_role_give_channel", description="Установить канал для логов выдачи/снятия ролей")
@app_commands.describe(channel="Канал для логирования")
@is_allowed_only()
async def set_role_give_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "role_give", channel.id)
    embed = discord.Embed(
        title="✅ Канал установлен", 
        description=f"Логи изменения ролей в {channel.mention}\n\n⚠️ **Важно:** Убедитесь, что бот имеет право **«Просматривать аудит логов»**", 
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_warns_channel", description="Установить канал для логов предупреждений")
@app_commands.describe(channel="Канал для логирования")
@is_allowed_only()
async def set_warns_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "warns", channel.id)
    embed = discord.Embed(title="✅ Канал установлен", description=f"Логи предупреждений в {channel.mention}", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_voice_channel", description="Установить канал для логов голосовых каналов")
@app_commands.describe(channel="Канал для логирования")
@is_allowed_only()
async def set_voice_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "voice", channel.id)
    embed = discord.Embed(title="✅ Канал установлен", description=f"Логи голосовых каналов в {channel.mention}", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_nickname_channel", description="Установить канал для логов смены никнеймов")
@app_commands.describe(channel="Канал для логирования")
@is_allowed_only()
async def set_nickname_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "nickname", channel.id)
    embed = discord.Embed(title="✅ Канал установлен", description=f"Логи смены никнеймов в {channel.mention}", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="show_log_channels", description="Показать настроенные каналы для логов")
@is_allowed_only()
async def show_log_channels(interaction: discord.Interaction):
    embed = discord.Embed(title="📋 Настроенные каналы логирования", color=discord.Color.blue(), timestamp=datetime.datetime.utcnow())
    
    channel_types = {
        "mod_actions": "🛡️ Действия модерации",
        "message_delete": "🗑️ Удаленные сообщения",
        "message_edit": "✏️ Измененные сообщения",
        "bulk_delete": "📦 Массовые удаления",
        "role_give": "👥 Изменение ролей (с указанием кто выдал)",
        "warns": "⚠️ Предупреждения",
        "voice": "🔊 Голосовые каналы",
        "nickname": "📝 Смена никнеймов"
    }
    
    configured = 0
    for key, name in channel_types.items():
        channel_id = data_manager.get_log_channel(interaction.guild_id, key)
        if channel_id:
            channel = interaction.guild.get_channel(channel_id)
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

# ==================== КОМАНДЫ ДЛЯ РОЛЕЙ ====================

@bot.tree.command(name="set_join_role", description="Установить роль для новых участников")
@app_commands.describe(role="Роль, которая будет выдаваться новым участникам")
@is_allowed_only()
async def set_join_role(interaction: discord.Interaction, role: discord.Role):
    data_manager.set_join_role(interaction.guild_id, role.id)
    embed = discord.Embed(title="✅ Роль установлена", description=f"Новые участники будут получать роль {role.mention}", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)
    await log_role_give(interaction.guild, f"⚙️ **Выдал:** {interaction.user.mention}\n**Пользователь:** Система\n**Действие:** Установил автоматическую выдачу роли {role.mention} для новичков", discord.Color.blue())

@bot.tree.command(name="remove_join_role", description="Отключить автоматическую выдачу роли")
@is_allowed_only()
async def remove_join_role(interaction: discord.Interaction):
    if data_manager.remove_join_role(interaction.guild_id):
        embed = discord.Embed(title="✅ Автовыдача отключена", description="Новые участники больше не будут получать роль автоматически", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
        await log_role_give(interaction.guild, f"⚙️ **Выдал:** {interaction.user.mention}\n**Пользователь:** Система\n**Действие:** Отключил автовыдачу роли", discord.Color.blue())
    else:
        await interaction.response.send_message("❌ Автовыдача роли не была настроена", ephemeral=True)

# ==================== КОМАНДЫ МОДЕРАЦИИ ====================

@bot.tree.command(name="kick", description="Кикнуть пользователя")
@app_commands.describe(member="Пользователь для кика", reason="Причина кика")
@is_allowed_only()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    try:
        await member.kick(reason=reason)
        embed = discord.Embed(title="👢 Пользователь кикнут", description=f"**Пользователь:** {member.mention}\n**ID:** `{member.id}`\n**Причина:** {reason}", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed)
        await log_mod_action(interaction.guild, f"👢 {interaction.user.mention} кикнул {member.mention}\nПричина: {reason}")
        data_manager.add_mod_log(interaction.guild_id, {"action": "kick", "moderator": interaction.user.id, "target": member.id, "reason": reason, "date": datetime.datetime.utcnow().isoformat()})
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="ban", description="Забанить пользователя")
@app_commands.describe(member="Пользователь для бана", reason="Причина бана")
@is_allowed_only()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    try:
        await member.ban(reason=reason, delete_message_days=0)
        embed = discord.Embed(title="🔨 Пользователь забанен", description=f"**Пользователь:** {member.mention}\n**ID:** `{member.id}`\n**Причина:** {reason}", color=discord.Color.red())
        await interaction.response.send_message(embed=embed)
        await log_mod_action(interaction.guild, f"🔨 {interaction.user.mention} забанил {member.mention}\nПричина: {reason}")
        data_manager.add_mod_log(interaction.guild_id, {"action": "ban", "moderator": interaction.user.id, "target": member.id, "reason": reason, "date": datetime.datetime.utcnow().isoformat()})
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="unban", description="Разбанить пользователя по ID")
@app_commands.describe(user_id="ID пользователя", reason="Причина разбана")
@is_allowed_only()
async def unban(interaction: discord.Interaction, user_id: str, reason: str = "Не указана"):
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=reason)
        embed = discord.Embed(title="🔓 Пользователь разбанен", description=f"**Пользователь:** {user.name}\n**ID:** `{user.id}`\n**Причина:** {reason}", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
        await log_mod_action(interaction.guild, f"🔓 {interaction.user.mention} разбанил {user.name}\nПричина: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="mute", description="Замутить пользователя")
@app_commands.describe(member="Пользователь для мута", minutes="Длительность в минутах", reason="Причина мута")
@is_allowed_only()
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Не указана"):
    try:
        duration = datetime.timedelta(minutes=minutes)
        await member.timeout(duration, reason=reason)
        embed = discord.Embed(title="🔇 Пользователь замучен", description=f"**Пользователь:** {member.mention}\n**ID:** `{member.id}`\n**Длительность:** {minutes} мин\n**Причина:** {reason}", color=discord.Color.dark_gray())
        await interaction.response.send_message(embed=embed)
        await log_mod_action(interaction.guild, f"🔇 {interaction.user.mention} замутил {member.mention} на {minutes} мин\nПричина: {reason}")
        data_manager.add_mod_log(interaction.guild_id, {"action": "mute", "moderator": interaction.user.id, "target": member.id, "reason": reason, "duration": minutes, "date": datetime.datetime.utcnow().isoformat()})
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="Снять мут с пользователя")
@app_commands.describe(member="Пользователь для снятия мута", reason="Причина")
@is_allowed_only()
async def unmute(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    try:
        await member.timeout(None, reason=reason)
        embed = discord.Embed(title="🔊 Мут снят", description=f"**Пользователь:** {member.mention}\n**ID:** `{member.id}`\n**Причина:** {reason}", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
        await log_mod_action(interaction.guild, f"🔊 {interaction.user.mention} снял мут с {member.mention}\nПричина: {reason}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="clear", description="Очистить сообщения в канале")
@app_commands.describe(amount="Количество сообщений для удаления")
@is_allowed_only()
async def clear(interaction: discord.Interaction, amount: int):
    try:
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        embed = discord.Embed(title="🧹 Сообщения удалены", description=f"Удалено **{len(deleted)}** сообщений", color=discord.Color.blue())
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_mod_action(interaction.guild, f"🧹 {interaction.user.mention} очистил {len(deleted)} сообщений в {interaction.channel.mention}")
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="warn", description="Выдать предупреждение пользователю")
@app_commands.describe(member="Пользователь", reason="Причина предупреждения")
@is_allowed_only()
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    warn_data = {"moderator": interaction.user.id, "reason": reason, "date": datetime.datetime.utcnow().isoformat()}
    data_manager.add_warn(interaction.guild_id, member.id, warn_data)
    warns_count = len(data_manager.get_warns(interaction.guild_id, member.id))
    
    embed = discord.Embed(title="⚠️ Предупреждение", description=f"**Пользователь:** {member.mention}\n**ID:** `{member.id}`\n**Предупреждений:** {warns_count}\n**Причина:** {reason}", color=discord.Color.yellow())
    await interaction.response.send_message(embed=embed)
    
    try:
        await member.send(f"Вы получили предупреждение на сервере **{interaction.guild.name}**\n**Причина:** {reason}")
    except:
        pass
    
    await log_warn(interaction.guild, f"⚠️ {interaction.user.mention} выдал предупреждение {member.mention}\nПричина: {reason}")

@bot.tree.command(name="warns", description="Показать предупреждения пользователя")
@app_commands.describe(member="Пользователь")
@is_allowed_only()
async def warns(interaction: discord.Interaction, member: discord.Member):
    warns_list = data_manager.get_warns(interaction.guild_id, member.id)
    
    if warns_list:
        embed = discord.Embed(title=f"Предупреждения: {member.display_name}", description=f"**ID:** `{member.id}`\n**Всего:** {len(warns_list)}", color=discord.Color.orange())
        for i, warn in enumerate(warns_list[-10:], 1):
            mod = bot.get_user(warn["moderator"])
            mod_name = mod.name if mod else f"ID: {warn['moderator']}"
            date = datetime.datetime.fromisoformat(warn["date"]).strftime("%d.%m.%Y %H:%M")
            embed.add_field(name=f"#{i} - {date}", value=f"**Модератор:** {mod_name}\n**Причина:** {warn['reason']}", inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(f"У пользователя {member.mention} нет предупреждений", ephemeral=True)

@bot.tree.command(name="mod_logs", description="Показать последние действия модерации")
@app_commands.describe(limit="Количество записей для показа")
@is_allowed_only()
async def mod_logs(interaction: discord.Interaction, limit: int = 10):
    logs = data_manager.get_mod_logs(interaction.guild_id)
    
    if logs:
        logs_to_show = logs[-limit:]
        embed = discord.Embed(title="📋 Последние действия модерации", color=discord.Color.blue(), timestamp=datetime.datetime.utcnow())
        
        for log in reversed(logs_to_show):
            date = datetime.datetime.fromisoformat(log["date"]).strftime("%d.%m.%Y %H:%M")
            duration_text = f" на {log['duration']} мин" if "duration" in log else ""
            embed.add_field(name=f"{log['action']}{duration_text} - {date}", value=f"**Модератор:** <@{log['moderator']}>\n**Пользователь:** <@{log['target']}>\n**Причина:** {log['reason']}", inline=False)
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Логи пока отсутствуют", ephemeral=True)

# ==================== КОМАНДЫ ДЛЯ КРАСИВЫХ СООБЩЕНИЙ ====================

@bot.tree.command(name="embed", description="Создать красивое сообщение в любой канал")
@app_commands.describe(
    channel="Канал для отправки",
    title="Заголовок сообщения",
    description="Основной текст сообщения",
    color="Цвет (red, green, blue, gold, purple, orange, yellow, pink)",
    thumbnail="URL миниатюры (опционально)",
    image="URL большого изображения (опционально)",
    footer="Текст внизу (опционально)",
    timestamp="Добавить время (True/False)"
)
@is_allowed_only()
async def slash_embed(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    description: str,
    color: str = "blue",
    thumbnail: Optional[str] = None,
    image: Optional[str] = None,
    footer: Optional[str] = None,
    timestamp: bool = False
):
    color_map = {
        "red": discord.Color.red(),
        "green": discord.Color.green(),
        "blue": discord.Color.blue(),
        "gold": discord.Color.gold(),
        "purple": discord.Color.purple(),
        "orange": discord.Color.orange(),
        "yellow": discord.Color.yellow(),
        "pink": discord.Color.magenta(),
    }
    
    embed_color = color_map.get(color.lower(), discord.Color.blue())
    
    embed = discord.Embed(title=title, description=description, color=embed_color)
    
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    if footer:
        embed.set_footer(text=footer)
    if timestamp:
        embed.timestamp = datetime.datetime.utcnow()
    
    await channel.send(embed=embed)
    await interaction.response.send_message(f"✅ Сообщение отправлено в {channel.mention}", ephemeral=True)


@bot.tree.command(name="embed_fields", description="Создать сообщение с несколькими полями")
@app_commands.describe(
    channel="Канал для отправки",
    title="Заголовок сообщения",
    fields="Поля в формате: Название1 | Текст1 || Название2 | Текст2",
    color="Цвет (red, green, blue, gold, purple, orange)",
    thumbnail="URL миниатюры (опционально)",
    image="URL изображения (опционально)",
    footer="Текст внизу (опционально)"
)
@is_allowed_only()
async def slash_embed_fields(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    fields: str,
    color: str = "blue",
    thumbnail: Optional[str] = None,
    image: Optional[str] = None,
    footer: Optional[str] = None
):
    color_map = {
        "red": discord.Color.red(),
        "green": discord.Color.green(),
        "blue": discord.Color.blue(),
        "gold": discord.Color.gold(),
        "purple": discord.Color.purple(),
        "orange": discord.Color.orange(),
    }
    embed_color = color_map.get(color.lower(), discord.Color.blue())
    
    embed = discord.Embed(title=title, color=embed_color, timestamp=datetime.datetime.utcnow())
    
    field_parts = fields.split("||")
    
    for field in field_parts:
        if "|" in field:
            name, value = field.split("|", 1)
            embed.add_field(name=name.strip(), value=value.strip(), inline=False)
    
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    if footer:
        embed.set_footer(text=footer)
    
    await channel.send(embed=embed)
    await interaction.response.send_message(f"✅ Сообщение с {len(field_parts)} полями отправлено в {channel.mention}", ephemeral=True)


@bot.tree.command(name="say", description="Быстро отправить красивое сообщение")
@app_commands.describe(
    channel="Канал для отправки",
    text="Текст сообщения",
    color="Цвет (red, green, blue, gold)",
    title="Заголовок (опционально)"
)
@is_allowed_only()
async def slash_say(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    text: str,
    color: str = "blue",
    title: Optional[str] = None
):
    color_map = {
        "red": discord.Color.red(),
        "green": discord.Color.green(),
        "blue": discord.Color.blue(),
        "gold": discord.Color.gold(),
    }
    embed_color = color_map.get(color.lower(), discord.Color.blue())
    
    embed = discord.Embed(
        title=title if title else None,
        description=text,
        color=embed_color
    )
    
    await channel.send(embed=embed)
    await interaction.response.send_message(f"✅ Сообщение отправлено в {channel.mention}", ephemeral=True)


@bot.tree.command(name="template_save", description="Сохранить шаблон сообщения")
@app_commands.describe(
    name="Название шаблона",
    title="Заголовок",
    description="Описание",
    color="Цвет",
    footer="Нижний колонтитул"
)
@is_allowed_only()
async def save_template(
    interaction: discord.Interaction,
    name: str,
    title: str,
    description: str,
    color: str = "blue",
    footer: Optional[str] = None
):
    template = {
        "title": title,
        "description": description,
        "color": color,
        "footer": footer,
        "created_by": interaction.user.id,
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    
    data_manager.save_embed_template(interaction.guild_id, name, template)
    await interaction.response.send_message(f"✅ Шаблон `{name}` сохранен!", ephemeral=True)


@bot.tree.command(name="template_send", description="Отправить сообщение из шаблона")
@app_commands.describe(
    channel="Канал для отправки",
    name="Название шаблона"
)
@is_allowed_only()
async def send_template(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    name: str
):
    template = data_manager.get_embed_template(interaction.guild_id, name)
    
    if not template:
        await interaction.response.send_message(f"❌ Шаблон `{name}` не найден!", ephemeral=True)
        return
    
    color_map = {
        "red": discord.Color.red(),
        "green": discord.Color.green(),
        "blue": discord.Color.blue(),
        "gold": discord.Color.gold(),
        "purple": discord.Color.purple(),
        "orange": discord.Color.orange(),
    }
    embed_color = color_map.get(template.get("color", "blue"), discord.Color.blue())
    
    embed = discord.Embed(
        title=template["title"],
        description=template["description"],
        color=embed_color,
        timestamp=datetime.datetime.utcnow()
    )
    
    if template.get("footer"):
        embed.set_footer(text=template["footer"])
    
    await channel.send(embed=embed)
    await interaction.response.send_message(f"✅ Шаблон `{name}` отправлен в {channel.mention}", ephemeral=True)


@bot.tree.command(name="template_list", description="Показать все сохраненные шаблоны")
@is_allowed_only()
async def list_templates(interaction: discord.Interaction):
    templates = data_manager.get_all_templates(interaction.guild_id)
    
    if not templates:
        await interaction.response.send_message("❌ Нет сохраненных шаблонов!", ephemeral=True)
        return
    
    embed = discord.Embed(title="📋 Сохраненные шаблоны", color=discord.Color.blue(), timestamp=datetime.datetime.utcnow())
    
    for name, template in templates.items():
        embed.add_field(name=f"📌 {name}", value=f"Заголовок: {template['title'][:50]}", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="template_delete", description="Удалить шаблон")
@app_commands.describe(name="Название шаблона")
@is_allowed_only()
async def delete_template(interaction: discord.Interaction, name: str):
    if data_manager.delete_embed_template(interaction.guild_id, name):
        await interaction.response.send_message(f"✅ Шаблон `{name}` удален!", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Шаблон `{name}` не найден!", ephemeral=True)


@bot.tree.command(name="test_role_log", description="Протестировать логирование ролей")
@is_allowed_only()
async def test_role_log(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    channel_id = data_manager.get_log_channel(interaction.guild_id, "role_give")
    if channel_id:
        channel = interaction.guild.get_channel(channel_id)
        if channel:
            test_embed = discord.Embed(
                title="🧪 ТЕСТ ЛОГИРОВАНИЯ РОЛЕЙ",
                description=f"Это тестовое сообщение для проверки канала логов ролей.\n\n"
                            f"**Канал:** {channel.mention}\n"
                            f"**ID канала:** `{channel.id}`\n\n"
                            f"Если вы видите это сообщение, то канал настроен правильно!\n\n"
                            f"**Формат логов ролей:**\n"
                            f"• Кто выдал/снял роль\n"
                            f"• Кому выдал/снял роль\n"
                            f"• Какую роль\n"
                            f"• Время действия",
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

# ==================== КОМАНДЫ ДЛЯ ЛИДЕРОВ ====================

@bot.tree.command(name="лидеры", description="📢 Отправить или обновить список лидеров")
@app_commands.describe(
    текст="Текст списка лидеров (можно использовать форматирование)"
)
@is_allowed_only()
async def leaders_list(interaction: discord.Interaction, текст: str):
    """Отправляет или обновляет список лидеров в канале"""
    
    leaders_channel = bot.get_channel(LEADERS_CHANNEL_ID)
    if not leaders_channel:
        await interaction.response.send_message(f"❌ Канал для лидеров не найден! ID: {LEADERS_CHANNEL_ID}", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="👑 СПИСОК ЛИДЕРОВ ФРАКЦИЙ",
        description=текст,
        color=discord.Color.gold(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_author(
        name=interaction.user.name,
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    embed.set_footer(text="by Ilya Vetrov • Актуальный список лидеров")
    
    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)
    
    guild_id = str(interaction.guild_id)
    
    # Проверяем, есть ли уже сохраненное сообщение
    if guild_id in bot.leaders_messages and bot.leaders_messages[guild_id]:
        try:
            old_message_id = bot.leaders_messages[guild_id]
            old_message = await leaders_channel.fetch_message(old_message_id)
            await old_message.edit(embed=embed)
            await interaction.response.send_message(f"✅ Список лидеров **обновлен** в канале <#{LEADERS_CHANNEL_ID}>", ephemeral=True)
            return
        except:
            pass
    
    # Отправляем новое сообщение
    message = await leaders_channel.send(embed=embed)
    bot.leaders_messages[guild_id] = message.id
    await interaction.response.send_message(f"✅ Список лидеров **отправлен** в канал <#{LEADERS_CHANNEL_ID}>", ephemeral=True)


@bot.tree.command(name="сброс_лидеры", description="🔄 Сбросить ID сообщения лидеров (если сообщение было удалено)")
@is_allowed_only()
async def leaders_reset(interaction: discord.Interaction):
    """Сбрасывает сохраненный ID сообщения лидеров"""
    
    guild_id = str(interaction.guild_id)
    
    if guild_id in bot.leaders_messages:
        del bot.leaders_messages[guild_id]
        await interaction.response.send_message("✅ ID сообщения лидеров сброшен. При следующем использовании `/лидеры` создаст новое сообщение.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Нет сохраненного ID сообщения лидеров.", ephemeral=True)


@bot.tree.command(name="кураторы", description="📢 Отправить или обновить список кураторов")
@app_commands.describe(
    текст="Текст списка кураторов (можно использовать форматирование)"
)
@is_allowed_only()
async def curators_list(interaction: discord.Interaction, текст: str):
    """Отправляет или обновляет список кураторов в канале"""
    
    curators_channel = bot.get_channel(CURATOR_CHANNEL_ID)
    if not curators_channel:
        await interaction.response.send_message(f"❌ Канал для кураторов не найден! ID: {CURATOR_CHANNEL_ID}", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="👥 СПИСОК КУРАТОРОВ",
        description=текст,
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_author(
        name=interaction.user.name,
        icon_url=interaction.user.avatar.url if interaction.user.avatar else None
    )
    embed.set_footer(text="by Ilya Vetrov • Актуальный список кураторов")
    
    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)
    
    # Для кураторов пока не делаем сохранение ID, просто отправляем
    await curators_channel.send(embed=embed)
    await interaction.response.send_message(f"✅ Список кураторов **отправлен** в канал <#{CURATOR_CHANNEL_ID}>", ephemeral=True)


@bot.tree.command(name="help", description="Показать список команд")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 Команды модерационного бота", description="**Автор: by Ilya Vetrov**\nГлавный администратор имеет абсолютные права на всех серверах.", color=discord.Color.blue())
    
    embed.add_field(name="🎨 Красивые сообщения (только для главных админов)", 
                    value="`/embed` - создать красивое сообщение\n`/embed_fields` - с полями\n`/say` - быстрое сообщение\n`/template_save` - сохранить шаблон\n`/template_send` - отправить из шаблона\n`/template_list` - список шаблонов\n`/template_delete` - удалить шаблон", 
                    inline=False)
    
    embed.add_field(name="🛡️ Модерация",
                    value="`/kick` - кикнуть\n`/ban` - забанить\n`/unban` - разбанить\n`/mute` - замутить\n`/unmute` - снять мут\n`/clear` - очистить чат\n`/warn` - выдать предупреждение\n`/warns` - список предупреждений\n`/mod_logs` - история действий",
                    inline=False)
    
    embed.add_field(name="⚙️ Настройка логов",
                    value="`/setup_all_logs` - быстрая настройка всех каналов\n`/set_mod_log_channel` - логи модерации\n`/set_message_delete_channel` - удаленные сообщения\n`/set_message_edit_channel` - измененные сообщения\n`/set_bulk_delete_channel` - массовые удаления\n`/set_role_give_channel` - выдача ролей (с указанием кто выдал)\n`/set_warns_channel` - предупреждения\n`/set_voice_channel` - голосовые каналы\n`/set_nickname_channel` - смена ников\n`/show_log_channels` - показать настройки\n`/test_role_log` - тест логов ролей",
                    inline=False)
    
    embed.add_field(name="👋 Автовыдача ролей",
                    value="`/set_join_role` - установить роль для новичков\n`/remove_join_role` - отключить автовыдачу",
                    inline=False)
    
    embed.add_field(name="📢 Списки",
                    value="`/лидеры` - отправить/обновить список лидеров\n`/сброс_лидеры` - сбросить ID сообщения лидеров\n`/кураторы` - отправить список кураторов",
                    inline=False)
    
    embed.set_footer(text="by Ilya Vetrov • Все настройки сохраняются автоматически")
    await interaction.response.send_message(embed=embed)

# ==================== СОБЫТИЯ ====================

@bot.event
async def on_member_join(member):
    # Приветствие
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
            
            embed = discord.Embed(title="👋 ДОБРО ПОЖАЛОВАТЬ!", description=welcome_text, color=discord.Color.green())
            embed.set_footer(text="by Ilya Vetrov")
            await channel.send(f"{member.mention}", embed=embed)
            
            try:
                await member.send(embed=embed)
                logger.info(f"📨 Отправлено ЛС пользователю {member.name}")
            except:
                logger.warning(f"❌ Не удалось отправить ЛС {member.name}")
    
    # Автовыдача роли
    role_id = data_manager.get_join_role(member.guild.id)
    if role_id:
        role = member.guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role, reason="Автовыдача роли при заходе")
                logger.info(f"✅ Выдана роль {role.name} пользователю {member.name}")
            except Exception as e:
                logger.error(f"❌ Ошибка выдачи роли: {e}")

@bot.event
async def on_message_edit(before, after):
    await log_message_edit(before, after)

@bot.event
async def on_bulk_message_delete(messages):
    await log_bulk_delete(messages)

@bot.event
async def on_member_update(before, after):
    if before.bot or not before.guild:
        return
    
    # Логирование смены никнейма
    if before.nick != after.nick:
        await log_nickname(before.guild, f"📝 {before.mention} (`{before.id}`) **сменил никнейм**\n**Было:** `{before.nick or before.name}`\n**Стало:** `{after.nick or after.name}`")
    
    # Логирование изменений ролей с определением кто выдал/снял
    before_roles = set(before.roles)
    after_roles = set(after.roles)
    
    added_roles = after_roles - before_roles
    for role in added_roles:
        if role.name != "@everyone":
            moderator_info = await get_role_moderator(before.guild, before, role, "add")
            description = f"{moderator_info}\n**Пользователь:** {before.mention} (`{before.id}`)\n**Получил роль:** {role.mention}\n**ID роли:** `{role.id}`"
            await log_role_give(before.guild, description, discord.Color.green())
    
    removed_roles = before_roles - after_roles
    for role in removed_roles:
        if role.name != "@everyone":
            moderator_info = await get_role_moderator(before.guild, before, role, "remove")
            description = f"{moderator_info}\n**Пользователь:** {before.mention} (`{before.id}`)\n**Лишился роли:** {role.mention}\n**ID роли:** `{role.id}`"
            await log_role_give(before.guild, description, discord.Color.red())

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    await log_message_delete(message.guild, message)

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot or not member.guild:
        return
    
    if before.channel is None and after.channel is not None:
        await log_voice(member.guild, f"🔊 {member.mention} (`{member.id}`) **зашел** в голосовой канал {after.channel.mention}", discord.Color.green())
    elif before.channel is not None and after.channel is None:
        await log_voice(member.guild, f"🔇 {member.mention} (`{member.id}`) **вышел** из голосового канала {before.channel.mention}", discord.Color.red())
    elif before.channel != after.channel:
        await log_voice(member.guild, f"🔄 {member.mention} (`{member.id}`) **переместился** из {before.channel.mention} в {after.channel.mention}", discord.Color.blue())

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.send("❌ Только администраторы могут использовать эту команду!")

# ==================== ПРЕФИКСНЫЕ КОМАНДЫ ====================

@bot.command(name='синхронизировать')
async def sync_command(ctx):
    if ctx.author.id in MAIN_ADMIN_IDS:
        await bot.tree.sync()
        await ctx.send("✅ Слэш-команды синхронизированы! by Ilya Vetrov")
    else:
        await ctx.send("❌ Только администраторы!")

@bot.command(name='статус')
async def status_command(ctx):
    if ctx.author.id in MAIN_ADMIN_IDS:
        embed = discord.Embed(title="🤖 СТАТУС БОТА", color=discord.Color.blue(), timestamp=datetime.datetime.utcnow())
        embed.add_field(name="📱 Имя бота", value=f"```{bot.user.name}```", inline=True)
        embed.add_field(name="🆔 ID", value=f"```{bot.user.id}```", inline=True)
        embed.add_field(name="🌐 Серверов", value=f"```{len(bot.guilds)}```", inline=True)
        embed.add_field(name="⚙️ Автовыдача ролей", value=f"```{len(data_manager.settings['join_roles'])} серверов```", inline=True)
        
        total_channels = sum(len(channels) for channels in data_manager.settings["log_channels"].values())
        embed.add_field(name="📋 Каналов логов", value=f"```{total_channels}```", inline=True)
        
        total_warns = sum(len(warns) for warns in data_manager.settings["warns"].values())
        embed.add_field(name="⚠️ Предупреждений", value=f"```{total_warns}```", inline=True)
        
        uptime = datetime.datetime.utcnow() - bot.start_time
        days = uptime.days
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        embed.add_field(name="⏱️ Время работы", value=f"```{days}д {hours}ч {minutes}м```", inline=True)
        
        embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ Только администраторы!")

@bot.command(name='бэкап')
async def backup_command(ctx):
    if ctx.author.id in MAIN_ADMIN_IDS:
        await ctx.send("🔄 Создание бэкапа настроек...")
        
        backup_data = data_manager.settings
        backup_file = f"full_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join('/tmp', backup_file)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=4)
            
            with open(filepath, 'rb') as f:
                await ctx.send(
                    content=f"✅ **Полный бэкап настроек создан!**\n📅 Дата: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
                    file=discord.File(f, filename=backup_file)
                )
            
            os.remove(filepath)
        except Exception as e:
            await ctx.send(f"❌ Ошибка при создании бэкапа: {e}")
    else:
        await ctx.send("❌ Только главный администратор может создавать бэкапы!")

# ==================== ЗАПУСК ====================

if __name__ == "__main__":
    token = os.getenv('TOKEN')
    
    if not token:
        print("❌ ОШИБКА: Токен не найден в переменных окружения!")
        exit(1)
    
    print("🔄 Запуск бота...")
    try:
        bot.run(token)
    except discord.LoginFailure:
        print("❌ ОШИБКА: Неправильный токен бота!")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
