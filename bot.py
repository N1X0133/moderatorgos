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

# ==================== УЛУЧШЕННАЯ СИСТЕМА ХРАНЕНИЯ ДАННЫХ ====================

class PersistentDataManager:
    """Менеджер данных с защитой от потери при обновлении"""
    
    def __init__(self):
        # Основная папка для данных (не будет удаляться при обновлении)
        self.data_folder = '/app/data'
        
        # Папка для резервных копий
        self.backup_folder = os.path.join(self.data_folder, 'backups')
        
        # Блокировка для потокобезопасности
        self._lock = Lock()
        
        # Создаем необходимые папки
        self.ensure_folders()
        
        # Загружаем настройки
        self.settings = self.load_settings()
        
    def ensure_folders(self):
        """Создает необходимые папки"""
        os.makedirs(self.data_folder, exist_ok=True)
        os.makedirs(self.backup_folder, exist_ok=True)
        logger.info(f"📁 Папки данных: {self.data_folder}")
        
    def load_settings(self):
        """Загружает все настройки из JSON файлов"""
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
            "guild_prefixes": {},
            "auto_moderation": {},
            "custom_commands": {}
        }
        
        try:
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # Конвертируем строковые ключи обратно в int для guild_id
                    for key in ['join_roles', 'mod_logs', 'warns', 'guild_prefixes', 'auto_moderation', 'custom_commands']:
                        if key in loaded:
                            loaded[key] = {int(k) if k.isdigit() else k: v for k, v in loaded[key].items()}
                    
                    # Конвертируем log_channels
                    if 'log_channels' in loaded:
                        for log_type in loaded['log_channels']:
                            loaded['log_channels'][log_type] = {
                                int(k) if k.isdigit() else k: v 
                                for k, v in loaded['log_channels'][log_type].items()
                            }
                    
                    logger.info(f"✅ Загружены настройки из {settings_file}")
                    return loaded
            else:
                logger.info(f"📝 Файл настроек не найден, создаем новый")
                self.save_settings(default_settings)
                return default_settings
                
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки настроек: {e}")
            # Пытаемся восстановить из бэкапа
            return self.restore_from_backup()
    
    def save_settings(self, settings=None):
        """Сохраняет настройки с созданием бэкапа"""
        with self._lock:
            if settings is None:
                settings = self.settings
            
            # Добавляем метаданные
            settings["version"] = "2.0"
            settings["last_updated"] = datetime.datetime.utcnow().isoformat()
            
            settings_file = os.path.join(self.data_folder, 'bot_settings.json')
            
            # Создаем бэкап перед сохранением
            if os.path.exists(settings_file):
                backup_file = os.path.join(
                    self.backup_folder, 
                    f"bot_settings_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                )
                try:
                    import shutil
                    shutil.copy2(settings_file, backup_file)
                    # Оставляем только последние 10 бэкапов
                    self.cleanup_old_backups()
                except Exception as e:
                    logger.error(f"⚠️ Не удалось создать бэкап: {e}")
            
            # Сохраняем новые настройки
            try:
                # Конвертируем int ключи в строки для JSON
                save_data = self._prepare_for_json(settings)
                
                with open(settings_file, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, ensure_ascii=False, indent=4)
                logger.info(f"💾 Настройки сохранены в {settings_file}")
                return True
            except Exception as e:
                logger.error(f"❌ Ошибка сохранения настроек: {e}")
                return False
    
    def _prepare_for_json(self, data):
        """Подготавливает данные для JSON сериализации"""
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                # Конвертируем int ключи в строки
                new_key = str(k) if isinstance(k, int) else k
                result[new_key] = self._prepare_for_json(v)
            return result
        elif isinstance(data, list):
            return [self._prepare_for_json(item) for item in data]
        else:
            return data
    
    def restore_from_backup(self):
        """Восстанавливает настройки из последнего бэкапа"""
        try:
            backups = [f for f in os.listdir(self.backup_folder) if f.startswith('bot_settings_backup_')]
            if backups:
                latest_backup = sorted(backups)[-1]
                backup_file = os.path.join(self.backup_folder, latest_backup)
                with open(backup_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # Конвертируем обратно
                    for key in ['join_roles', 'mod_logs', 'warns']:
                        if key in loaded:
                            loaded[key] = {int(k): v for k, v in loaded[key].items() if k.isdigit()}
                    logger.info(f"🔄 Восстановлены настройки из бэкапа: {latest_backup}")
                    return loaded
        except Exception as e:
            logger.error(f"❌ Не удалось восстановить из бэкапа: {e}")
        
        # Возвращаем настройки по умолчанию
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
            "guild_prefixes": {},
            "auto_moderation": {},
            "custom_commands": {}
        }
        return default_settings
    
    def cleanup_old_backups(self, keep=10):
        """Оставляет только последние N бэкапов"""
        try:
            backups = [f for f in os.listdir(self.backup_folder) if f.startswith('bot_settings_backup_')]
            backups.sort()
            
            while len(backups) > keep:
                oldest = backups.pop(0)
                os.remove(os.path.join(self.backup_folder, oldest))
                logger.info(f"🗑️ Удален старый бэкап: {oldest}")
        except Exception as e:
            logger.error(f"⚠️ Ошибка при очистке бэкапов: {e}")
    
    # Методы для удобного доступа к настройкам
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
        
        # Ограничиваем размер логов
        if len(self.settings["mod_logs"][guild_id]) > 1000:
            self.settings["mod_logs"][guild_id] = self.settings["mod_logs"][guild_id][-1000:]
        
        self.save_settings()
    
    def export_settings(self, guild_id=None):
        """Экспорт настроек для бэкапа"""
        if guild_id:
            # Экспорт только для конкретного сервера
            export_data = {
                "guild_id": guild_id,
                "export_date": datetime.datetime.utcnow().isoformat(),
                "join_role": self.settings["join_roles"].get(guild_id),
                "log_channels": {},
                "warns": self.settings["warns"].get(guild_id, {}),
                "mod_logs": self.settings["mod_logs"].get(guild_id, [])
            }
            
            for log_type, channels in self.settings["log_channels"].items():
                if guild_id in channels:
                    export_data["log_channels"][log_type] = channels[guild_id]
            
            return export_data
        else:
            # Экспорт всех настроек
            return self.settings

# Инициализируем менеджер данных
data_manager = PersistentDataManager()

class ModerationBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.initial_extensions = []
        self.data_manager = data_manager
        self.start_time = datetime.datetime.utcnow()
        
    async def setup_hook(self):
        # Синхронизация слеш-команд
        await self.tree.sync()
        logger.info("✅ Слеш-команды синхронизированы")
        
    async def on_ready(self):
        # Информационная панель при запуске
        print("\n" + "="*60)
        print("🤖 МОДЕРАЦИОННЫЙ БОТ ЗАПУЩЕН")
        print("="*60)
        print(f"📱 Имя бота: {self.user.name}")
        print(f"🆔 ID бота: {self.user.id}")
        print(f"🌐 Серверов: {len(self.guilds)}")
        print(f"👑 Главный администратор: {MAIN_ADMIN_ID}")
        print(f"👨‍💻 Автор: by Ilya Vetrov")
        print(f"📅 Время запуска: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
        print(f"💾 Версия данных: {self.data_manager.settings.get('version', '1.0')}")
        print("="*60)
        
        # Выводим статистику настроек
        total_log_channels = sum(
            len(channels) for channels in self.data_manager.settings["log_channels"].values()
        )
        total_join_roles = len(self.data_manager.settings["join_roles"])
        total_warns = sum(len(warns) for warns in self.data_manager.settings["warns"].values())
        
        print(f"\n📊 Статистика настроек:")
        print(f"   • Настроено каналов логов: {total_log_channels}")
        print(f"   • Серверов с автовыдачей: {total_join_roles}")
        print(f"   • Всего предупреждений: {total_warns}")
        print()
        
        await self.change_presence(activity=discord.Game(name="/help | Модерация by Ilya Vetrov"))

bot = ModerationBot()

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
    
    channel_id = data_manager.get_log_channel(guild.id, log_type)
    if channel_id:
        channel = guild.get_channel(channel_id)
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

# ==================== КОМАНДА ДЛЯ ЭКСПОРТА/ИМПОРТА НАСТРОЕК ====================

@bot.tree.command(name="export_settings", description="Экспортировать настройки сервера в JSON")
@is_admin_only()
async def slash_export_settings(interaction: discord.Interaction):
    """Экспорт настроек сервера"""
    await interaction.response.defer()
    
    export_data = data_manager.export_settings(interaction.guild_id)
    
    # Создаем файл
    filename = f"backup_{interaction.guild.name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join('/tmp', filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=4)
        
        with open(filepath, 'rb') as f:
            await interaction.followup.send(
                content="📦 **Экспорт настроек завершен!**\nФайл содержит все настройки сервера.",
                file=discord.File(f, filename=filename)
            )
        
        # Удаляем временный файл
        os.remove(filepath)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка при экспорте: {e}", ephemeral=True)

@bot.tree.command(name="import_settings", description="Импортировать настройки сервера из JSON файла")
@app_commands.describe(file="JSON файл с настройками")
@is_admin_only()
async def slash_import_settings(interaction: discord.Interaction, file: discord.Attachment):
    """Импорт настроек сервера"""
    await interaction.response.defer(ephemeral=True)
    
    if not file.filename.endswith('.json'):
        await interaction.followup.send("❌ Пожалуйста, загрузите JSON файл!", ephemeral=True)
        return
    
    try:
        # Скачиваем файл
        content = await file.read()
        import_data = json.loads(content.decode('utf-8'))
        
        # Проверяем, что файл для этого сервера
        if import_data.get("guild_id") != interaction.guild_id:
            await interaction.followup.send(
                "❌ Этот файл настроек предназначен для другого сервера!", 
                ephemeral=True
            )
            return
        
        # Восстанавливаем настройки
        if import_data.get("join_role"):
            data_manager.set_join_role(interaction.guild_id, import_data["join_role"])
        
        for log_type, channel_id in import_data.get("log_channels", {}).items():
            data_manager.set_log_channel(interaction.guild_id, log_type, channel_id)
        
        await interaction.followup.send(
            "✅ **Настройки успешно импортированы!**\n"
            f"• Роль для новичков: {'установлена' if import_data.get('join_role') else 'не установлена'}\n"
            f"• Каналов логов: {len(import_data.get('log_channels', {}))}",
            ephemeral=True
        )
        
    except json.JSONDecodeError:
        await interaction.followup.send("❌ Неверный формат JSON файла!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка при импорте: {e}", ephemeral=True)

@bot.tree.command(name="settings_info", description="Показать информацию о текущих настройках")
@is_admin_only()
async def slash_settings_info(interaction: discord.Interaction):
    """Показывает информацию о настройках"""
    embed = discord.Embed(
        title="ℹ️ Информация о настройках",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
    )
    
    # Версия настроек
    embed.add_field(
        name="📦 Версия данных",
        value=f"`{data_manager.settings.get('version', '1.0')}`",
        inline=True
    )
    
    # Последнее обновление
    last_updated = data_manager.settings.get('last_updated', 'Неизвестно')
    embed.add_field(
        name="🕐 Последнее обновление",
        value=f"`{last_updated[:19]}`",
        inline=True
    )
    
    # Статистика
    embed.add_field(
        name="📊 Статистика",
        value=f"**Серверов в БД:** {len(data_manager.settings['join_roles'])}\n"
              f"**Всего логов:** {sum(len(logs) for logs in data_manager.settings['mod_logs'].values())}\n"
              f"**Всего варнов:** {sum(len(warns) for warns in data_manager.settings['warns'].values())}",
        inline=False
    )
    
    embed.set_footer(text="by Ilya Vetrov • Настройки сохраняются автоматически")
    await interaction.response.send_message(embed=embed)

# ==================== СЛЕШ-КОМАНДЫ ДЛЯ НАСТРОЙКИ КАНАЛОВ ====================

@bot.tree.command(name="setup_all_logs", description="Быстрая настройка всех каналов для логов (укажите канал)")
@app_commands.describe(channel="Канал для всех логов")
@is_admin_only()
async def slash_setup_all_logs(interaction: discord.Interaction, channel: discord.TextChannel):
    """Устанавливает один канал для всех типов логов"""
    
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
                    f"• 📝 Смена никнеймов\n\n"
                    f"💾 **Настройки сохранены и не будут потеряны при обновлении бота!**",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_mod_log_channel", description="Установить канал для логов действий модерации")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_mod_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "mod_actions", channel.id)
    
    embed = discord.Embed(
        title="✅ Канал для модерации установлен",
        description=f"Действия модерации будут логироваться в {channel.mention}\n💾 Настройки сохранены!",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_message_delete_channel", description="Установить канал для логов удаленных сообщений")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_message_delete_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "message_delete", channel.id)
    
    embed = discord.Embed(
        title="✅ Канал для удаленных сообщений установлен",
        description=f"Удаленные сообщения будут логироваться в {channel.mention}\n💾 Настройки сохранены!",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_message_edit_channel", description="Установить канал для логов измененных сообщений")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_message_edit_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "message_edit", channel.id)
    
    embed = discord.Embed(
        title="✅ Канал для измененных сообщений установлен",
        description=f"Измененные сообщения будут логироваться в {channel.mention}\n💾 Настройки сохранены!",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_bulk_delete_channel", description="Установить канал для логов массовых удалений")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_bulk_delete_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "bulk_delete", channel.id)
    
    embed = discord.Embed(
        title="✅ Канал для массовых удалений установлен",
        description=f"Массовые удаления будут логироваться в {channel.mention}\n\n"
                    f"⚠️ **Важно:** Каждое удаленное сообщение будет показано отдельно!\n"
                    f"💾 Настройки сохранены!",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_role_give_channel", description="Установить канал для логов выдачи/снятия ролей")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_role_give_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "role_give", channel.id)
    
    embed = discord.Embed(
        title="✅ Канал для изменений ролей установлен",
        description=f"Выдача и снятие ролей будут логироваться в {channel.mention}\n\n"
                    f"⚠️ **Важно:** Убедитесь, что бот имеет право **«Просматривать аудит логов»** (View Audit Log) на сервере!\n\n"
                    f"📝 **Формат логов:**\n"
                    f"• Кто выдал/снял роль\n"
                    f"• Кому выдал/снял роль\n"
                    f"• Какая роль\n"
                    f"💾 Настройки сохранены!",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_warns_channel", description="Установить канал для логов предупреждений")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_warns_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "warns", channel.id)
    
    embed = discord.Embed(
        title="✅ Канал для предупреждений установлен",
        description=f"Предупреждения будут логироваться в {channel.mention}\n💾 Настройки сохранены!",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_voice_channel", description="Установить канал для логов голосовых каналов")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_voice_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "voice", channel.id)
    
    embed = discord.Embed(
        title="✅ Канал для голосовых каналов установлен",
        description=f"Входы/выходы из войс-каналов будут логироваться в {channel.mention}\n💾 Настройки сохранены!",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_nickname_channel", description="Установить канал для логов смены никнеймов")
@app_commands.describe(channel="Канал для логирования")
@is_admin_only()
async def slash_set_nickname_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data_manager.set_log_channel(interaction.guild_id, "nickname", channel.id)
    
    embed = discord.Embed(
        title="✅ Канал для смены никнеймов установлен",
        description=f"Смена никнеймов будет логироваться в {channel.mention}\n💾 Настройки сохранены!",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="show_log_channels", description="Показать настроенные каналы для логов")
@is_admin_only()
async def slash_show_log_channels(interaction: discord.Interaction):
    
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
    
    embed.add_field(
        name="📊 Статистика", 
        value=f"Настроено {configured} из {len(channel_types)} каналов\n💾 Данные сохранены в постоянном хранилище", 
        inline=False
    )
    embed.set_footer(text="by Ilya Vetrov • Настройка логов")
    await interaction.response.send_message(embed=embed)

# ==================== СЛЕШ-КОМАНДЫ ДЛЯ РОЛЕЙ ====================

@bot.tree.command(name="set_join_role", description="Установить роль для новых участников")
@app_commands.describe(role="Роль, которая будет выдаваться новым участникам")
@is_admin_only()
async def slash_set_join_role(interaction: discord.Interaction, role: discord.Role):
    data_manager.set_join_role(interaction.guild_id, role.id)
    
    embed = discord.Embed(
        title="✅ Роль установлена",
        description=f"Новые участники теперь будут получать роль {role.mention}\n💾 Настройки сохранены!",
        color=discord.Color.green()
    )
    embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="remove_join_role", description="Отключить автоматическую выдачу роли")
@is_admin_only()
async def slash_remove_join_role(interaction: discord.Interaction):
    if data_manager.remove_join_role(interaction.guild_id):
        embed = discord.Embed(
            title="✅ Автовыдача отключена",
            description="Новые участники больше не будут получать роль автоматически\n💾 Настройки сохранены!",
            color=discord.Color.green()
        )
        embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
        await interaction.response.send_message(embed=embed)
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
        
        # Сохраняем в лог
        data_manager.add_mod_log(interaction.guild_id, {
            "action": "kick",
            "moderator": interaction.user.id,
            "target": member.id,
            "reason": reason,
            "date": datetime.datetime.utcnow().isoformat()
        })
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
        
        data_manager.add_mod_log(interaction.guild_id, {
            "action": "ban",
            "moderator": interaction.user.id,
            "target": member.id,
            "reason": reason,
            "date": datetime.datetime.utcnow().isoformat()
        })
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
        
        data_manager.add_mod_log(interaction.guild_id, {
            "action": "unban",
            "moderator": interaction.user.id,
            "target": int(user_id),
            "reason": reason,
            "date": datetime.datetime.utcnow().isoformat()
        })
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
        
        data_manager.add_mod_log(interaction.guild_id, {
            "action": "mute",
            "moderator": interaction.user.id,
            "target": member.id,
            "reason": reason,
            "duration": minutes,
            "date": datetime.datetime.utcnow().isoformat()
        })
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
        
        data_manager.add_mod_log(interaction.guild_id, {
            "action": "unmute",
            "moderator": interaction.user.id,
            "target": member.id,
            "reason": reason,
            "date": datetime.datetime.utcnow().isoformat()
        })
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
        
        data_manager.add_mod_log(interaction.guild_id, {
            "action": "clear",
            "moderator": interaction.user.id,
            "target": 0,
            "reason": f"Очищено {len(deleted)} сообщений в {interaction.channel.name}",
            "date": datetime.datetime.utcnow().isoformat()
        })
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name="warn", description="Выдать предупреждение пользователю")
@app_commands.describe(member="Пользователь", reason="Причина предупреждения")
@is_admin_only()
async def slash_warn(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    
    warn_data = {
        "moderator": interaction.user.id,
        "reason": reason,
        "date": datetime.datetime.utcnow().isoformat()
    }
    
    data_manager.add_warn(interaction.guild_id, member.id, warn_data)
    
    warns_count = len(data_manager.get_warns(interaction.guild_id, member.id))
    
    embed = discord.Embed(
        title="⚠️ Предупреждение",
        description=f"**Пользователь:** {member.mention}\n**ID:** `{member.id}`\n**Предупреждений:** {warns_count}\n**Причина:** {reason}",
        color=discord.Color.yellow(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text=f"Модератор: {interaction.user} (`{interaction.user.id}`) • by Ilya Vetrov")
    await interaction.response.send_message(embed=embed)
    
    try:
        await member.send(f"Вы получили предупреждение на сервере **{interaction.guild.name}**\n**Причина:** {reason}\nВсего предупреждений: {warns_count}")
    except:
        pass
    
    await log_warn(interaction.guild, f"⚠️ {interaction.user.mention} (`{interaction.user.id}`) выдал предупреждение {member.mention} (`{member.id}`)\nПричина: {reason}")

@bot.tree.command(name="warns", description="Показать предупреждения пользователя")
@app_commands.describe(member="Пользователь")
@is_admin_only()
async def slash_warns(interaction: discord.Interaction, member: discord.Member):
    warns = data_manager.get_warns(interaction.guild_id, member.id)
    
    if warns:
        embed = discord.Embed(
            title=f"Предупреждения: {member.display_name}",
            description=f"**ID:** `{member.id}`\n**Всего:** {len(warns)}",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.utcnow()
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
    logs = data_manager.get_mod_logs(interaction.guild_id)
    
    if logs:
        logs_to_show = logs[-limit:]
        
        embed = discord.Embed(
            title="📋 Последние действия модерации",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
        
        for log in reversed(logs_to_show):
            date = datetime.datetime.fromisoformat(log["date"]).strftime("%d.%m.%Y %H:%M")
            duration_text = f" на {log['duration']} мин" if "duration" in log else ""
            embed.add_field(
                name=f"{log['action']}{duration_text} - {date}",
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
        description="**Автор: by Ilya Vetrov**\nГлавный администратор имеет абсолютные права на всех серверах.\n\n**Все команды доступны только администраторам сервера!**\n\n💾 **Все настройки автоматически сохраняются и не теряются при обновлении бота!**",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
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
              "`/set_role_give_channel` - выдача/снятие ролей (с указанием кто выдал)\n"
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
        name="💾 Управление настройками",
        value="`/export_settings` - экспортировать настройки сервера\n"
              "`/import_settings` - импортировать настройки сервера\n"
              "`/settings_info` - информация о настройках",
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
    
    embed.add_field(name="⚙️ Автовыдача ролей", value=f"```{len(data_manager.settings['join_roles'])} серверов```", inline=True)
    
    total_channels = sum(len(channels) for channels in data_manager.settings["log_channels"].values())
    embed.add_field(name="📋 Каналов логов", value=f"```{total_channels}```", inline=True)
    
    total_warns = sum(len(warns) for warns in data_manager.settings["warns"].values())
    embed.add_field(name="⚠️ Всего предупреждений", value=f"```{total_warns}```", inline=True)
    
    embed.add_field(name="💾 Версия данных", value=f"```{data_manager.settings.get('version', '1.0')}```", inline=True)
    
    uptime = datetime.datetime.utcnow() - bot.start_time
    days = uptime.days
    hours = uptime.seconds // 3600
    minutes = (uptime.seconds % 3600) // 60
    
    embed.add_field(name="⏱️ Время работы", value=f"```{days}д {hours}ч {minutes}м```", inline=True)
    
    embed.set_footer(text="by Ilya Vetrov • Модерационный бот")
    
    await ctx.send(embed=embed)

@bot.command(name='бэкап')
async def backup_command(ctx):
    """Создать бэкап настроек"""
    if ctx.author.id != MAIN_ADMIN_ID:
        await ctx.send("❌ Только главный администратор может создавать бэкапы!")
        return
    
    await ctx.send("🔄 Создание бэкапа настроек...")
    
    # Создаем полный бэкап
    backup_data = data_manager.export_settings()
    backup_file = f"full_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join('/tmp', backup_file)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=4)
        
        with open(filepath, 'rb') as f:
            await ctx.send(
                content="✅ **Полный бэкап настроек создан!**\n"
                       f"📅 Дата: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                       f"💾 Размер: {os.path.getsize(filepath) / 1024:.2f} KB",
                file=discord.File(f, filename=backup_file)
            )
        
        os.remove(filepath)
        
    except Exception as e:
        await ctx.send(f"❌ Ошибка при создании бэкапа: {e}")

# ==================== ОБРАБОТЧИКИ СОБЫТИЙ ====================

@bot.event
async def on_member_join(member):
    """Приветствие при заходе нового участника"""
    
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
async def on_member_update(before, after):
    """Логирование изменений профиля пользователя (роли и никнеймы)"""
    if before.bot or not before.guild:
        return
    
    # Логирование смены никнейма
    if before.nick != after.nick:
        channel_id = data_manager.get_log_channel(before.guild.id, "nickname")
        if channel_id:
            channel = before.guild.get_channel(channel_id)
            if channel:
                old_nick = before.nick or before.name
                new_nick = after.nick or after.name
                
                embed = discord.Embed(
                    title="📝 СМЕНА НИКНЕЙМА",
                    description=f"**Пользователь:** {before.mention} (`{before.id}`)\n"
                                f"**Было:** `{old_nick}`\n"
                                f"**Стало:** `{new_nick}`",
                    color=discord.Color.teal(),
                    timestamp=datetime.datetime.utcnow()
                )
                embed.set_footer(text="by Ilya Vetrov • Смена ника")
                await channel.send(embed=embed)
    
    # Логирование изменений ролей
    before_roles = set(before.roles)
    after_roles = set(after.roles)
    
    # Выданные роли
    added_roles = after_roles - before_roles
    for role in added_roles:
        if role.name != "@everyone":
            # Получаем информацию о том, кто выдал роль
            moderator_info = await get_role_moderator(before.guild, before, role, "add")
            embed = discord.Embed(
                description=f"{moderator_info}\n"
                            f"**Пользователь:** {before.mention} (`{before.id}`)\n"
                            f"**Получил роль:** {role.mention}\n"
                            f"**ID роли:** `{role.id}`",
                color=discord.Color.green(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text="by Ilya Vetrov • Выдача роли")
            await send_to_log_channel(before.guild, "role_give", embed)
    
    # Снятые роли
    removed_roles = before_roles - after_roles
    for role in removed_roles:
        if role.name != "@everyone":
            # Получаем информацию о том, кто снял роль
            moderator_info = await get_role_moderator(before.guild, before, role, "remove")
            embed = discord.Embed(
                description=f"{moderator_info}\n"
                            f"**Пользователь:** {before.mention} (`{before.id}`)\n"
                            f"**Лишился роли:** {role.mention}\n"
                            f"**ID роли:** `{role.id}`",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text="by Ilya Vetrov • Снятие роли")
            await send_to_log_channel(before.guild, "role_give", embed)

async def get_role_moderator(guild, target, role, action_type):
    """
    Получает информацию о том, кто выдал/снял роль из аудит-лога
    action_type: "add" для выдачи, "remove" для снятия
    """
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

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot or not member.guild:
        return
    
    channel_id = data_manager.get_log_channel(member.guild.id, "voice")
    if not channel_id:
        return
    
    channel = member.guild.get_channel(channel_id)
    if not channel:
        return
    
    if before.channel is None and after.channel is not None:
        embed = discord.Embed(
            description=f"🔊 {member.mention} (`{member.id}`) **зашел** в голосовой канал {after.channel.mention}",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="by Ilya Vetrov • Голосовые каналы")
        await channel.send(embed=embed)
    
    elif before.channel is not None and after.channel is None:
        embed = discord.Embed(
            description=f"🔇 {member.mention} (`{member.id}`) **вышел** из голосового канала {before.channel.mention}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="by Ilya Vetrov • Голосовые каналы")
        await channel.send(embed=embed)
    
    elif before.channel != after.channel:
        embed = discord.Embed(
            description=f"🔄 {member.mention} (`{member.id}`) **переместился** из {before.channel.mention} в {after.channel.mention}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text="by Ilya Vetrov • Голосовые каналы")
        await channel.send(embed=embed)

@bot.event
async def on_message_delete(message):
    """Логирование удаленных сообщений"""
    if message.author.bot or not message.guild:
        return
    
    channel_id = data_manager.get_log_channel(message.guild.id, "message_delete")
    if not channel_id:
        return
    
    channel = message.guild.get_channel(channel_id)
    if not channel:
        return
    
    embed = discord.Embed(
        title="🗑 СООБЩЕНИЕ УДАЛЕНО",
        color=discord.Color.red(),
        timestamp=datetime.datetime.utcnow()
    )
    
    author_text = f"{message.author.mention}\nID: `{message.author.id}`\nИмя: `{message.author.name}`"
    embed.add_field(name="👤 Автор", value=author_text, inline=True)
    
    channel_text = f"{message.channel.mention}\nID: `{message.channel.id}`"
    embed.add_field(name="📌 Канал", value=channel_text, inline=True)
    
    if message.content:
        content = message.content[:1000] + "..." if len(message.content) > 1000 else message.content
        embed.add_field(name="📝 Содержание", value=f"```{content}```", inline=False)
    
    embed.set_footer(text=f"by Ilya Vetrov • ID сообщения: {message.id}")
    await channel.send(embed=embed)

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
    print("\n" + "="*60)
    print("🔄 ЗАГРУЗКА МОДЕРАЦИОННОГО БОТА")
    print("="*60)
    
    print("📂 Загрузка данных...")
    # Данные уже загружены в data_manager при инициализации
    
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
