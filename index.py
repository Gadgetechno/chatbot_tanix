import logging
import asyncio
import os
import random
import re
import ssl
import certifi
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
import httpx

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    InputMediaPhoto
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    ContextTypes, 
    ConversationHandler,
    filters
)
from telegram.error import BadRequest, TelegramError, NetworkError
from telegram.request import HTTPXRequest
import google.generativeai as genai

# ==============================
# LOGGING SETUP
# ==============================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================
# GEMINI AI CONFIGURATION
# ==============================
GEMINI_API_KEY = "AIzaSyBYtKz6t_NLaOZ9HkxLTzaNOYE7b2IcMWk"
genai.configure(api_key=GEMINI_API_KEY)

gemini_model = genai.GenerativeModel("gemini-2.5-flash")

async def get_gemini_response(user_message: str, context: str = "") -> str:
    """Get response from Gemini AI with Hindi-English mix."""
    try:
        prompt = f"""
        You are a helpful trading mentor assistant speaking in Hinglish (Hindi + English mix).
        User context: {context}
        User message: {user_message}
        
        Respond in Hinglish with:
        - Friendly "bro" tone
        - Simple, easy-to-understand language
        - Focus on learning and skill development
        - Encouraging and positive
        - Keep response under 5-10 words
        
        If user asks about:
        - Learning Trading: Share learning roadmap, suggest YouTube videos, ask about their progress
        - Trading Strategy: Guide them to learn chart patterns, Tanix AI methods
        - Progress: Ask what they've learned, encourage them to keep practicing
        - Risk/Loss/Money Management: ONLY discuss if user DIRECTLY asks, otherwise redirect to learning
        - Registration: Guide to use the bot's registration link and YouTube tutorials
        - Anything else: Be helpful and friendly, focus on growth and learning
        
        AVOID mentioning risks, losses, or money management UNLESS user directly asks.
        """
        
        response = gemini_model.generate_content(prompt)
        return response.text[:500]
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return "Sorry bro, technical issue aa gaya. Thodi der baad try karna ya /start command fir se use karna."

# ==============================
# MOTIVATIONAL MESSAGES
# ==============================
MOTIVATIONAL_MESSAGES = [
    "Remember, consistency is key in trading. Keep learning, keep growing! 📈",
    "Har din thoda time trading ke liye dedo, results automatically dikhne lageinge! 💪",
    "Keep learning new patterns and strategies. Practice makes perfect! 📚",
    "Trading me patience rakhna seekho. Market kabhi bhi opportunity deti hai! ⏳",
    "Small wins bhi celebrate karo! Stay consistent and keep practicing! 🏆",
    "Discipline se trading karo, aur Tanix AI roadmap follow karo, success zaroor milegi! 🧠",
    "Har successful trader pehle beginner tha. Tum bhi ban sakte ho! 🚀",
    "YouTube videos dekho aur daily practice karo. Skills develop ho jayengi! 📹",
    "Market ki movement samajhna seekho, chart patterns study karo. You'll do great! 🔍",
    "Keep a trading journal. It's the best way to track progress and improve! 📝"
]

# ==============================
# ENCOURAGING MESSAGES FOR PERIODIC CHECK-INS
# ==============================
ENCOURAGING_MESSAGES = [
    "Kaise chal raha hai trading practice? Aaj kuch naya seekha? 📊",
    "Trading journey me consistency important hai. Keep learning! 💪",
    "Remember, slow and steady wins the race. Daily thoda time deke seekho. 📈",
    "Aaj YouTube pe koi naya video dekha? Learning journey kaisa chal raha hai? 📹",
    "Trading me patience key hai. Keep practicing! 🚀",
    "Aaj kuch naya seekha trading ke baare mein? Share karna chahenge toh batana!",
    "Chart patterns practice kar rahe ho? Keep learning and growing! 👍",
    "Tanix AI roadmap follow kar rahe ho? Progress kaisa hai? 🎯",
    "Daily thoda practice zaroori hai. Keep it up! Skills improve ho rahi hain!",
    "YouTube channel dekho aur practice karo. You're doing amazing! 💯"
]

# ==============================
# EDUCATIONAL MESSAGES FOR UNDERAGE USERS
# ==============================
EDUCATIONAL_MESSAGES = [
    "Kya kuch naya seekha aaj trading ke baare mein? Hamare YouTube channel pe beginner tutorials hain! 📺",
    "Yaad rakhna: Paper trading sabse best practice hai. Tumhara virtual portfolio kaise chal raha hai? 📊",
    "Market analysis hamare Telegram channel pe post kiya hai! Real money risk kiye bina seekhne ka best tareeka. 💬",
    "Knowledge paise se zyada tezi se grow karti hai. Daily learning continue rakho! 🧠",
    "Paper trading practice me koi interesting strategy mili? Share karna chahenge toh batana!",
    "Weekend learning tip: Candlestick patterns padho - yeh technical analysis ki foundation hai! 📈",
    "Tumhara trading journal kaise chal raha hai? Paper trades track karna improvement ka key hai! 📝",
    "Risk management seekhna trading se bhi important hai. Hamare channel pe iske baare mein videos hain! 🛡️",
    "Patience trading me sabse bada superpower hai. Keep learning! 💪",
    "Trading psychology padho - yeh sabse underrated skill hai successful traders ka! 🧘‍♂️"
]

# ==============================
# DAILY FOLLOW-UP QUESTIONS
# ==============================
DAILY_QUESTIONS = [
    "Aaj ka din kaisa raha? 😊",
    "Aaj trading ki ya nahi? 📊",
    "Aaj profit hua ya loss? 💰",
    "Aaj koi nayi strategy try ki? 🔍",
    "Aaj market se kya seekha? 📚",
    "Aaj emotional control kaisa raha? 🧠",
    "Aaj risk management properly follow kiya? 🛡️",
    "Aaj kitna time dedicate kiya trading ko? ⏰",
    "Aaj trading journal update kiya? 📝",
    "Aaj ka sabse bada learning kya raha? 🎓"
]

# ==============================
# CONVERSATION STATES
# ==============================
(
    START, WAITING_FOR_NAME, WAITING_FOR_AGE, WAITING_FOR_EXPERIENCE, SHOWING_PROOF,
    WAITING_FOR_READY, WAITING_FOR_SOURCE, REGISTRATION_STEP,
    WAITING_FOR_DONE, WAITING_FOR_UNDERAGE_RESPONSE,
    DAILY_FOLLOWUP, WAITING_TRADING_STATUS, WAITING_PROFIT_LOSS,
    WAITING_FOR_ACCOUNT_STATUS, WAITING_FOR_TRADER_ID, WAITING_FOR_AMOUNT,
    WAITING_FOR_ADMIN_APPROVAL
) = range(17)

# Admin state management (separate from user conversations)
admin_awaiting_reply = {}

# ==============================
# CONFIGURATION
# ==============================
class BotConfig:
    def __init__(self):
        # URLs
        self.TELEGRAM_CHANNEL = "https://t.me/TANISHQTRADER"
        self.YOUTUBE_CHANNEL = "https://youtube.com/@LEARNWITHTANISHQ1"
        self.REVIEWS_LINK = "https://t.me/your_reviews_channel"
        self.TRADING_LINK = "https://u3.shortink.io/register?utm_campaign=834817&utm_source=affiliate&utm_medium=sr&a=POY4xB1cswM8K7&ac=bo"
        self.TRADING_LINK_GLOBAL = "https://u3.shortink.io/register?utm_campaign=834817&utm_source=affiliate&utm_medium=sr&a=POY4xB1cswM8K7&ac=bo"
        
        # Media files
        self.INTRO_VIDEO = "intro_video.mp4"
        self.PROOF_VOICE = "proof_voice.m4a"
        self.PROOF_IMAGES = [
            "proof1.png",
            "proof2.png", 
            "proof3.png",
            "proof4.png",
            "proof5.png",
            "proof6.png",
            "proof7.png",
            "proof8.png",
            "proof9.png",
            "proof10.png",
            "proof11.png",
        ]
        
        # Validate files exist
        self.validate_files()
        
    def validate_files(self):
        """Check if media files exist."""
        if not os.path.exists(self.INTRO_VIDEO):
            logger.warning(f"Intro video not found: {self.INTRO_VIDEO}")
            
        for img in self.PROOF_IMAGES:
            if not os.path.exists(img):
                logger.warning(f"Proof image not found: {img}")
    
    def validate_urls(self) -> bool:
        """Validate all URLs before using them."""
        urls = [
            self.TELEGRAM_CHANNEL,
            self.YOUTUBE_CHANNEL,
            self.REVIEWS_LINK,
            self.TRADING_LINK,
            self.TRADING_LINK_GLOBAL
        ]
        
        for url in urls:
            if not url or not url.startswith('https://'):
                logger.error(f"Invalid URL: {url}")
                return False
        return True

config = BotConfig()

# ==============================
# ADMIN CONFIGURATION
# ==============================
ADMIN_ID = 1076818877

# Pending trader ID verifications
pending_verifications: Dict[int, Dict] = {}

# ==============================
# USER SESSION MANAGEMENT
# ==============================
class UserSession:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.state = START
        self.name: Optional[str] = None
        self.age: Optional[str] = None
        self.experience: Optional[str] = None
        self.source: Optional[str] = None
        self.registration_time: Optional[datetime] = None
        self.last_checkin: Optional[datetime] = None
        self.last_daily_followup: Optional[datetime] = None
        self.conversation_history: List[str] = []
        self.is_underage: bool = False
        self.daily_response_count: int = 0
        self.last_trading_day: Optional[datetime] = None
        self.total_profits: float = 0.0
        self.total_losses: float = 0.0
        self.trading_days: int = 0
        self.has_trading_account: Optional[bool] = None
        self.trader_id: Optional[str] = None
        self.account_created_with_link: Optional[bool] = None
        self.last_activity: Optional[datetime] = datetime.now()
        self.reminder_count: int = 0
        self.last_reminder_sent: Optional[datetime] = None
        
    def update_state(self, new_state: int):
        self.state = new_state
        self.last_activity = datetime.now()
        self.reminder_count = 0  # Reset reminder count on state change
        logger.info(f"User {self.user_id}: State {self.state}")
        
    def add_to_history(self, message: str, is_user: bool = False):
        """Add message to conversation history."""
        prefix = "User: " if is_user else "Bot: "
        self.conversation_history.append(f"{prefix}{message}")
        if len(self.conversation_history) > 20:
            self.conversation_history.pop(0)

# Session storage
user_sessions: Dict[int, UserSession] = {}

def get_user_session(user_id: int) -> UserSession:
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession(user_id)
    return user_sessions[user_id]

# ==============================
# MESSAGE PACING UTILITIES
# ==============================
async def slow_send_message(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    delay: float = 1.5,
    **kwargs
) -> Optional[int]:
    """Send message with natural human-like delay."""
    try:
        if len(text) > 50:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="typing"
            )
            await asyncio.sleep(0.5)
        
        await asyncio.sleep(delay)
        
        if update.callback_query:
            message = await update.callback_query.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                **kwargs
            )
        else:
            message = await update.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                **kwargs
            )
        
        session = get_user_session(update.effective_user.id)
        session.add_to_history(text)
        
        return message.message_id
        
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return None

async def send_video_with_delay(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    video_path: str,
    caption: str,
    delay: float = 2.0
):
    """Send video with natural delay."""
    await asyncio.sleep(delay)
    
    if os.path.exists(video_path):
        with open(video_path, 'rb') as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=caption,
                parse_mode='HTML'
            )
    else:
        await slow_send_message(update, context, caption)

async def send_video_with_delay_and_pin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    video_path: str,
    caption: str,
    delay: float = 2.0
):
    """Send video note (circular video) with natural delay and pin it."""
    await asyncio.sleep(delay)
    
    try:
        if os.path.exists(video_path):
            with open(video_path, 'rb') as video_file:
                # Send as video note (circular video)
                message = await update.message.reply_video_note(
                    video_note=video_file
                )
                # Pin the video note message
                await context.bot.pin_chat_message(
                    chat_id=update.effective_chat.id,
                    message_id=message.message_id,
                    disable_notification=True
                )
                logger.info(f"Pinned intro video note for user {update.effective_user.id}")
                
                # Send caption as separate message since video notes don't support captions
                await asyncio.sleep(0.5)
                await update.message.reply_text(caption)
                
                return message
        else:
            message_id = await slow_send_message(update, context, caption)
            if message_id:
                await context.bot.pin_chat_message(
                    chat_id=update.effective_chat.id,
                    message_id=message_id,
                    disable_notification=True
                )
            return message_id
    except Exception as e:
        logger.error(f"Error pinning video note message: {e}")
        # Continue even if pinning fails
        if os.path.exists(video_path):
            with open(video_path, 'rb') as video_file:
                message = await update.message.reply_video_note(
                    video_note=video_file
                )
                await asyncio.sleep(0.5)
                await update.message.reply_text(caption)
                return message
        else:
            await slow_send_message(update, context, caption)

async def send_images_with_delay(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_paths: List[str],
    caption: str
):
    """Send multiple images with delays."""
    session = get_user_session(update.effective_user.id)
    session.update_state(SHOWING_PROOF)
    
    await slow_send_message(
        update, context,
        "📸 Real Student Proofs aa rahe hain...",
        delay=1.0
    )
    
    await asyncio.sleep(2.0)
    
    valid_images = [img for img in image_paths if os.path.exists(img)]
    
    if not valid_images:
        await slow_send_message(
            update, context,
            caption,
            delay=1.0
        )
        return
    
    try:
        with open(valid_images[0], 'rb') as img_file:
            await update.message.reply_photo(
                photo=img_file,
                caption=caption,
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Error sending image: {e}")
    
    for img_path in valid_images[1:]:
        await asyncio.sleep(1.5)
        try:
            with open(img_path, 'rb') as img_file:
                await update.message.reply_photo(photo=img_file)
        except Exception as e:
            logger.error(f"Error sending image {img_path}: {e}")
            continue

# ==============================
# DAILY FOLLOW-UP SYSTEM
# ==============================
async def send_daily_followup(context: ContextTypes.DEFAULT_TYPE):
    """Send daily follow-up questions to users."""
    current_time = datetime.now()
    
    for user_id, session in list(user_sessions.items()):
        try:
            # Only send to users who completed registration
            if session.registration_time and not session.is_underage:
                # Check if it's a new day (after 9 AM)
                if current_time.hour >= 9:
                    # Check if we haven't sent today's followup yet
                    if not session.last_daily_followup or \
                       (current_time - session.last_daily_followup) >= timedelta(hours=24):
                        
                        # Personalized greeting
                        greeting = f"Good morning"
                        if session.name:
                            greeting += f" {session.name}"
                        greeting += "! ☀️"
                        
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"{greeting}\n{random.choice(MOTIVATIONAL_MESSAGES)}"
                        )
                        
                        await asyncio.sleep(2)
                        
                        # Send daily question
                        question = random.choice(DAILY_QUESTIONS)
                        session.state = DAILY_FOLLOWUP
                        
                        if "profit" in question.lower() or "loss" in question.lower():
                            # For profit/loss questions
                            keyboard = InlineKeyboardMarkup([
                                [
                                    InlineKeyboardButton("✅ Profit Hua", callback_data='daily_profit'),
                                    InlineKeyboardButton("❌ Loss Hua", callback_data='daily_loss')
                                ],
                                [
                                    InlineKeyboardButton("🤔 Break-even Raha", callback_data='daily_break_even'),
                                    InlineKeyboardButton("📊 Trading Nahi Ki", callback_data='daily_no_trade')
                                ]
                            ])
                        elif "trading" in question.lower():
                            # For trading yes/no questions
                            keyboard = InlineKeyboardMarkup([
                                [
                                    InlineKeyboardButton("✅ Haan, Trading Ki", callback_data='daily_traded_yes'),
                                    InlineKeyboardButton("❌ Nahin, Trading Nahi Ki", callback_data='daily_traded_no')
                                ]
                            ])
                        else:
                            # For general questions
                            keyboard = InlineKeyboardMarkup([
                                [
                                    InlineKeyboardButton("😊 Accha Raha", callback_data='daily_good'),
                                    InlineKeyboardButton("😐 Theek Thaak", callback_data='daily_ok'),
                                    InlineKeyboardButton("😔 Behtar Kar Sakta Tha", callback_data='daily_could_better')
                                ]
                            ])
                        
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=question,
                            reply_markup=keyboard
                        )
                        
                        session.last_daily_followup = current_time
                        session.daily_response_count += 1
                        session.add_to_history(f"Daily followup: {question}")
                        
                        logger.info(f"Sent daily followup to user {user_id}")
                        
        except Exception as e:
            logger.error(f"Error in daily followup for user {user_id}: {e}")
            continue

# ==============================
# INACTIVITY REMINDER SYSTEM
# ==============================
async def send_inactivity_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Send reminders to users who haven't responded in conversation."""
    current_time = datetime.now()
    
    for user_id, session in list(user_sessions.items()):
        try:
            # Skip users who are registered or not in conversation
            if session.registration_time or session.state == START:
                continue
            
            # Skip underage users who declined
            if session.is_underage and session.state == ConversationHandler.END:
                continue
            
            if not session.last_activity:
                continue
            
            time_inactive = (current_time - session.last_activity).total_seconds() / 60
            
            # First reminder after 10 minutes
            if 10 <= time_inactive < 15 and session.reminder_count == 0:
                reminder_msg = get_reminder_message(session, first_reminder=True)
                
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=reminder_msg
                    )
                    session.reminder_count = 1
                    session.last_reminder_sent = current_time
                    logger.info(f"Sent first reminder to user {user_id} in state {session.state}")
                except Exception as e:
                    logger.error(f"Error sending first reminder to {user_id}: {e}")
            
            # Second reminder after 30 minutes total (20 minutes after first)
            elif time_inactive >= 30 and session.reminder_count == 1:
                if session.last_reminder_sent:
                    time_since_last_reminder = (current_time - session.last_reminder_sent).total_seconds() / 60
                    
                    if time_since_last_reminder >= 20:
                        reminder_msg = get_reminder_message(session, first_reminder=False)
                        
                        try:
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=reminder_msg
                            )
                            session.reminder_count = 2
                            session.last_reminder_sent = current_time
                            logger.info(f"Sent second reminder to user {user_id} in state {session.state}")
                        except Exception as e:
                            logger.error(f"Error sending second reminder to {user_id}: {e}")
        
        except Exception as e:
            logger.error(f"Error in reminder system for user {user_id}: {e}")
            continue

def get_reminder_message(session: UserSession, first_reminder: bool = True) -> str:
    """Generate appropriate reminder message based on user state."""
    
    personalized_msg = "bro"
    if session.name:
        personalized_msg = session.name
    
    if first_reminder:
        # First reminder - encouraging
        if session.state == WAITING_FOR_NAME:
            return (
                f"Hey! Kya hua? 😊\n\n"
                f"Main abhi bhi yahan hoon! Trading journey start karne ke liye bas apna naam batao.\n\n"
                f"Agar koi doubt hai toh poochh sakte ho! 💬"
            )
        
        elif session.state == WAITING_FOR_AGE:
            return (
                f"Hey {personalized_msg}! 👋\n\n"
                f"Kya soch rahe ho? Age batane me koi hesitation nahi hona chahiye! 😊\n\n"
                f"Bas apni age bata do, aage badh sakte hain. Yeh sirf verification ke liye hai.\n\n"
                f"Main yahan wait kar raha hoon! ⏳"
            )
        
        elif session.state == WAITING_FOR_ACCOUNT_STATUS:
            return (
                f"Hey {personalized_msg}! 🤔\n\n"
                f"Trading account ke baare me poochha tha...\n\n"
                f"Kya tumhare paas already trading account hai? Bas button click karo:\n"
                f"✅ Haan ya ❌ Nahi\n\n"
                f"Don't worry, dono cases me main help karunga! 💪"
            )
        
        elif session.state == WAITING_FOR_TRADER_ID:
            return (
                f"Hey {personalized_msg}! 📱\n\n"
                f"Trader ID bhejne me koi problem aa rahi hai kya? 🤔\n\n"
                f"Agar Trader ID dhundhne me help chahiye:\n"
                f"1. Pocket Option app/website kholo\n"
                f"2. Profile section me jao\n"
                f"3. Trader ID wahan clearly dikhega\n"
                f"4. Woh ID yahan copy-paste kar do\n\n"
                f"Main yahan help ke liye hoon! 🙌"
            )
        
        elif session.state == WAITING_FOR_ADMIN_APPROVAL:
            return (
                f"Hey {personalized_msg}! ⏳\n\n"
                f"Tumhara verification request admin ke paas hai.\n\n"
                f"Thoda aur wait karo, jald hi approval mil jayega! 🚀\n\n"
                f"Meanwhile, tum hamare channels check kar sakte ho trading tips ke liye! 📺"
            )
        
        elif session.state == WAITING_FOR_UNDERAGE_RESPONSE:
            return (
                f"Hey {personalized_msg}! 🎓\n\n"
                f"Trading seekhna great decision hai!\n\n"
                f"Kya tum free educational content ke saath continue karna chahte ho?\n\n"
                f"✅ Button click karke batao! Main yahan wait kar raha hoon. 😊"
            )
        
        else:
            return (
                f"Hey {personalized_msg}! 👋\n\n"
                f"Kya ho gaya? Koi doubt hai kya? 🤔\n\n"
                f"Main yahan help ke liye hoon! Continue karte hain trading journey! 🚀\n\n"
                f"Agar stuck ho toh /start type karke fir se shuru kar sakte ho."
            )
    
    else:
        # Second reminder - more personal and encouraging
        if session.state == WAITING_FOR_NAME:
            return (
                f"Hey friend! 🌟\n\n"
                f"Main samajh sakta hoon ki kabhi kabhi busy ho jate hain! 😊\n\n"
                f"But trading journey start karna hai toh apna naam batana zaroori hai.\n\n"
                f"Bas ek message me apna naam bhejo aur lets get started! 🚀\n\n"
                f"Agar abhi time nahi hai toh no problem, jab bhi free ho tab continue karenge! 💯"
            )
        
        elif session.state == WAITING_FOR_AGE:
            return (
                f"{personalized_msg}, still here! 😊\n\n"
                f"Age verify karna zaroori hai kyunki:\n"
                f"• 18+ ke liye real trading guidance\n"
                f"• Under 18 ke liye educational content\n\n"
                f"Bas apni age bata do, koi judgment nahi hai! 🙌\n\n"
                f"Main help karne ke liye ready hoon! 💪"
            )
        
        elif session.state == WAITING_FOR_TRADER_ID:
            return (
                f"{personalized_msg}, I'm still here for you! 🤝\n\n"
                f"Trader ID verify karna last step hai successful registration ka!\n\n"
                f"Agar koi confusion hai ya help chahiye toh directly message karo.\n\n"
                f"Main personally guide karunga! 📞\n\n"
                f"Let's complete this together! 💪🔥"
            )
        
        elif session.state == WAITING_FOR_ADMIN_APPROVAL:
            return (
                f"{personalized_msg}! 🎯\n\n"
                f"Tumhara verification process chal raha hai.\n\n"
                f"Admin jald hi dekh lega aur approve kar dega! ✅\n\n"
                f"Meanwhile relaxed raho aur excited raho trading journey ke liye! 🚀\n\n"
                f"I'll notify you as soon as you're approved! 🔔"
            )
        
        else:
            return (
                f"{personalized_msg}! 💙\n\n"
                f"Main abhi bhi yahan hoon tumhari help ke liye!\n\n"
                f"Agar koi problem aa rahi hai toh batao, main solve kar dunga! 🛠️\n\n"
                f"Ya agar restart karna chahte ho toh /start type karo.\n\n"
                f"Let's make your trading journey successful! 🎯🔥"
            )

# ==============================
# PERIODIC CHECK-IN SYSTEM
# ==============================
async def periodic_checkin(context: ContextTypes.DEFAULT_TYPE):
    """Send periodic encouraging messages to users."""
    current_time = datetime.now()
    
    for user_id, session in list(user_sessions.items()):
        try:
            if session.is_underage:
                # Educational check-ins for underage users (less frequent)
                time_since_last = current_time - (session.last_checkin or datetime.now())
                
                if time_since_last >= timedelta(hours=12):
                    message = random.choice(EDUCATIONAL_MESSAGES)
                    
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton("📺 YouTube Channel", url=config.YOUTUBE_CHANNEL),
                        InlineKeyboardButton("💬 Telegram Channel", url=config.TELEGRAM_CHANNEL)
                    ]])
                    
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        reply_markup=keyboard
                    )
                    
                    session.last_checkin = current_time
                    session.add_to_history(f"Educational checkin: {message}")
                    
            else:
                # Original check-in logic for 18+ users
                if session.registration_time:
                    time_since_last = current_time - (session.last_checkin or session.registration_time)
                    
                    if time_since_last >= timedelta(minutes=30):
                        if random.random() < 0.5:
                            # Personalized message
                            personalized_msg = ""
                            if session.name:
                                personalized_msg = f"{session.name}, "
                            
                            message = f"{personalized_msg}{random.choice(ENCOURAGING_MESSAGES)}"
                            
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=message
                            )
                            
                            session.last_checkin = current_time
                            session.add_to_history(f"Auto-checkin: {message}")
                        
        except Exception as e:
            logger.error(f"Error in checkin for user {user_id}: {e}")
            continue

# ==============================
# DAILY RESPONSE HANDLERS
# ==============================
async def handle_daily_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle daily follow-up responses."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    session = get_user_session(user_id)
    
    # Reset state
    session.state = START
    
    # Handle different response types
    if query.data == 'daily_profit':
        await query.edit_message_text("🎉 Badhai ho! Profit acha feeling deta hai. Keep it up! 💰")
        
        # Ask for amount (optional)
        await asyncio.sleep(1)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💰 Amount Batana Chahta Hoon", callback_data='share_amount'),
                InlineKeyboardButton("🤫 Private Rakhunga", callback_data='keep_private')
            ]
        ])
        
        await slow_send_message(
            update, context,
            "Kya tum amount share karna chahte ho? (Optional)",
            reply_markup=keyboard
        )
        
        session.last_trading_day = datetime.now()
        session.trading_days += 1
        
    elif query.data == 'daily_loss':
        await query.edit_message_text("😔 Koi baat nahi! Loss trading ka part hai. Important hai ki tum seekho kya galti hui. 📚")
        
        # Motivational follow-up
        await asyncio.sleep(1)
        await slow_send_message(
            update, context,
            "Yaad rakhna:\n"
            "1. Stop loss use kiya?\n"
            "2. Risk management follow kiya?\n"
            "3. Emotion control kiya?\n\n"
            "Har loss se seekhne ka mauka milta hai! 💪",
            delay=1.0
        )
        
        session.last_trading_day = datetime.now()
        session.trading_days += 1
        
    elif query.data == 'daily_break_even':
        await query.edit_message_text("🤝 Break-even bhi accha hai! Risk nahi liya aur experience mila. Win-win situation! ✅")
        
    elif query.data == 'daily_no_trade':
        await query.edit_message_text("👍 Theek hai! Sometimes not trading is the best trade. Market me patience important hai! ⏳")
        
    elif query.data == 'daily_traded_yes':
        await query.edit_message_text("👏 Accha hai! Consistency maintain karna important hai. Keep going! 📈")
        
        # Follow-up question
        await asyncio.sleep(1)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Profit Hua", callback_data='daily_profit'),
                InlineKeyboardButton("❌ Loss Hua", callback_data='daily_loss')
            ],
            [
                InlineKeyboardButton("🤔 Break-even Raha", callback_data='daily_break_even')
            ]
        ])
        
        await slow_send_message(
            update, context,
            "Aur result kaisa raha?",
            reply_markup=keyboard
        )
        return WAITING_PROFIT_LOSS
        
    elif query.data == 'daily_traded_no':
        await query.edit_message_text("👍 Theek hai! Kabhi kabhi market me opportunity nahi hoti. Better opportunities wait karo! 🔍")
        
    elif query.data == 'daily_good':
        await query.edit_message_text("😊 Wah! Acha sunke khushi hui. Keep up the positive energy! ✨")
        
    elif query.data == 'daily_ok':
        await query.edit_message_text("👍 Theek hai! Kal aur behtar hoga. Keep trying! 💪")
        
    elif query.data == 'daily_could_better':
        await query.edit_message_text("🧠 Self-awareness acchi baat hai! Improvement ki jagah identify karna success ki pehli step hai. 📊")
        
    elif query.data == 'share_amount':
        await query.edit_message_text("Accha! Amount yaha reply karo:")
        session.state = WAITING_FOR_AMOUNT
        return WAITING_FOR_AMOUNT
        
    elif query.data == 'keep_private':
        await query.edit_message_text("👍 Samajh gaya. Important hai ki profit hua! Keep it up! 🚀")
    
    # Send motivational quote
    await asyncio.sleep(2)
    await send_motivational_quote(update, context, session.name)
    
    return ConversationHandler.END

async def handle_amount_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle profit amount response."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    
    try:
        amount_text = update.message.text.strip()
        # Try to extract number from text
        numbers = re.findall(r'\d+', amount_text)
        
        if numbers:
            amount = float(numbers[0])
            session.total_profits += amount
            
            personalized_msg = "bro"
            if session.name:
                personalized_msg = session.name
            
            await slow_send_message(
                update, context,
                f"🎉 Wah {personalized_msg}! ₹{amount:,.2f} profit! Badhai ho! Consistency rakho aur grow karte raho! 💰📈",
                delay=1.0
            )
        else:
            await slow_send_message(
                update, context,
                "👍 Accha hai profit hua! Keep tracking your progress! 📊",
                delay=1.0
            )
    except:
        await slow_send_message(
            update, context,
            "👍 Accha hai profit hua! Keep up the good work! 🚀",
            delay=1.0
        )
    
    # Reset state
    session.state = START
    
    # Send motivational quote
    await asyncio.sleep(2)
    await send_motivational_quote(update, context, session.name)
    
    return ConversationHandler.END

async def send_motivational_quote(update: Update, context: ContextTypes.DEFAULT_TYPE, user_name: Optional[str] = None):
    """Send motivational quote after daily response."""
    motivational_quotes = [
        "Remember: The stock market is a device for transferring money from the impatient to the patient. - Warren Buffett ⏳",
        "Trading mein 3 cheeze important hain: Patience, Discipline, Risk Management! 🧠",
        "Risk ko manage karna seekho, market ko predict karne ki koshish mat karo! 🛡️",
        "Small consistent profits > Occasional big profits! 📊",
        "Your biggest trading weapon is your psychology. Control your emotions! 🧘‍♂️",
        "Learn from your losses, they're your best teachers! 📚",
        "Trading is not about being right all the time, it's about making money over time! 💰",
        "The market will test your patience. Stay calm and stick to your plan! 🌊",
        "Success in trading = 20% Strategy + 80% Psychology! 🎯",
        "Keep learning, keep growing. The market always has something new to teach! 🎓"
    ]
    
    quote = random.choice(motivational_quotes)
    
    # Personalize if we have user name
    if user_name:
        quote = f"{user_name}, " + quote
    
    # Add trading tips for registered users
    session = get_user_session(update.effective_user.id)
    if session.registration_time and session.trading_days > 0:
        win_rate = (session.total_profits / max(session.total_profits + session.total_losses, 1)) * 100
        
        additional_tip = f"\n\n📊 Your Progress:\n"
        additional_tip += f"• Trading Days: {session.trading_days}\n"
        if session.total_profits > 0:
            additional_tip += f"• Total Profits: ₹{session.total_profits:,.2f}\n"
        additional_tip += f"• Keep up the consistency! 💪"
        
        quote += additional_tip
    
    if update.callback_query:
        await update.callback_query.message.reply_text(quote)
    else:
        await update.message.reply_text(quote)

# ==============================
# STEP HANDLERS WITH HUMANIZED PACING
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start command with video."""
    user = update.effective_user
    session = get_user_session(user.id)
    session.update_state(START)
    
    # Clear old data but keep progress stats
    session.name = None
    session.age = None
    session.experience = None
    session.source = None
    session.is_underage = False
    session.has_trading_account = None
    session.trader_id = None
    session.account_created_with_link = None
    
    logger.info(f"New user started: {user.id} ({user.username})")
    
    caption = (
        "Welcome ❤️\n"
        " Agr trading se paisa kamana hai To upper wala video note sunne ke baad  Tanix ai ki process karke Trader Id  Send kar dena Jiski madad se aap ajse he paisa kamana shuru kar doge !"
    )
    
    video_msg = await send_video_with_delay_and_pin(update, context, config.INTRO_VIDEO, caption)
    
    await asyncio.sleep(2.5)
    
    return await step_channels(update, context)

async def step_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Step 2: Channel join CTA."""
    
    await asyncio.sleep(1.0)
    
    buttons = []
    
    if config.validate_urls():
        if config.TELEGRAM_CHANNEL.startswith('https://'):
            buttons.append([InlineKeyboardButton(
                "💬 JOIN TELEGRAM CHANNEL", 
                url=config.TELEGRAM_CHANNEL
            )])
        
        if config.YOUTUBE_CHANNEL.startswith('https://'):
            buttons.append([InlineKeyboardButton(
                "🎥 JOIN YOUTUBE CHANNEL", 
                url=config.YOUTUBE_CHANNEL
            )])
    
    if buttons:
        keyboard = InlineKeyboardMarkup(buttons)
        msg_id = await slow_send_message(
            update, context,
            "Join my channels now and let's get started 🤝🔥",
            reply_markup=keyboard,
            delay=1.5
        )
        # Pin the channel links message
        try:
            if msg_id:
                await context.bot.pin_chat_message(
                    chat_id=update.effective_chat.id,
                    message_id=msg_id,
                    disable_notification=True
                )
                logger.info(f"Pinned channel links for user {update.effective_user.id}")
        except Exception as e:
            logger.error(f"Error pinning channel links: {e}")
    else:
        await slow_send_message(
            update, context,
            "Join my channels to get started! 🤝🔥",
            delay=1.5
        )
    
    await asyncio.sleep(2.0)
    
    return await step_proof_section(update, context)

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle name input."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    
    # Store name
    name_text = update.message.text.strip()
    session.name = name_text
    session.add_to_history(f"Name: {name_text}", is_user=True)
    
    logger.info(f"User {user_id} name: {name_text}")
    
    # Update state
    session.update_state(WAITING_FOR_AGE)
    
    # Acknowledge with personalized message
    await asyncio.sleep(0.8)
    await slow_send_message(
        update, context,
        f"Accha {name_text}! Nice to meet you! 👋",
        delay=1.0
    )
    
    # Ask age question
    await asyncio.sleep(1.5)
    await slow_send_message(
        update, context,
        f"{name_text}, tumhari age kya hai?",
        delay=1.0
    )
    
    return WAITING_FOR_AGE

async def step_proof_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 3: Proof section with real images."""
    caption = (
        "Yeh sab real students ke results hain ✅\n"
        "No fake promises, only real learning + discipline."
    )
    
    await send_images_with_delay(
        update, context,
        config.PROOF_IMAGES,
        caption
    )
    
    # Send voice note after images
    await asyncio.sleep(2)
    if os.path.exists(config.PROOF_VOICE):
        with open(config.PROOF_VOICE, 'rb') as voice_file:
            # Send as audio for MP4/M4A files, voice for OGG
            if config.PROOF_VOICE.endswith(('.mp4', '.m4a')):
                await update.effective_chat.send_audio(
                    audio=voice_file
                )
            else:
                await update.effective_chat.send_voice(
                    voice=voice_file
                )
    else:
        logger.warning(f"Voice note not found: {config.PROOF_VOICE}")
    
    # Send text message after voice note
    await asyncio.sleep(2)
    text_message = (
        "💲JUST FOLLOW THIS 3 STEPS:\n\n"
        "1️⃣CREATE NEW POCKET OPTION ACCOUNT THROUGH THIS LINK:\n"
        "🔗 https://u3.shortink.io/register?utm_campaign=834817&utm_source=affiliate&utm_medium=sr&a=POY4xB1cswM8K7&ac=bo\n\n"
        "2️⃣DEPOSIT MINIMUM $150\n"
        "YOU WILL GET BONUS\n\n"
        "3️⃣SEND ME YOUR TRADER ID ➖@TANISHBAIRAGI✅"
    )
    await slow_send_message(update, context, text_message, delay=1.0)
    
    # Send additional message about Tanix AI videos with YouTube buttons
    await asyncio.sleep(2)
    additional_message = (
        "If you don't know about Tanix AI you can watch these videos. 📹"
    )
    
    keyboard = [
        [InlineKeyboardButton("TANIX AI 2.0", url="https://youtu.be/-dpkZ31NrBk")],
        [InlineKeyboardButton("TANIX AI", url="https://youtu.be/iN_ygkoZ4m4")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.effective_chat.send_message(
        text=additional_message,
        reply_markup=reply_markup
    )
    
    # Ask for name after Tanix AI buttons
    await asyncio.sleep(2.0)
    await slow_send_message(
        update, context,
        "Accha bro, sabse pehle tumhara naam kya hai? 😊",
        delay=1.0
    )
    
    session = get_user_session(update.effective_user.id)
    session.update_state(WAITING_FOR_NAME)
    return WAITING_FOR_NAME

async def handle_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle age input with validation and educational guidance."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    
    age_text = update.message.text.strip()
    
    try:
        age = int(age_text)
        
        if age < 18:
            session.age = age_text
            session.is_underage = True
            session.add_to_history(f"Age: {age_text} (Under 18)", is_user=True)
            
            logger.info(f"User {user_id} is under 18: {age_text} years")
            
            personalized_msg = "bro"
            if session.name:
                personalized_msg = session.name
            
            await asyncio.sleep(0.8)
            
            await slow_send_message(
                update, context,
                f"Accha {personalized_msg}! {age_text} saal. Trading me interest dikhana acchi baat hai! 👍",
                delay=1.0
            )
            
            await asyncio.sleep(1.5)
            
            await slow_send_message(
                update, context,
                f"{personalized_msg}, tum 18 saal se kam ho, isliye main tumhe kuch important advice doonga: 📚",
                delay=1.0
            )
            
            await asyncio.sleep(1.5)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📺 YouTube Channel", url=config.YOUTUBE_CHANNEL)],
                [InlineKeyboardButton("💬 Telegram Channel", url=config.TELEGRAM_CHANNEL)]
            ])
            
            await slow_send_message(
                update, context,
                "1️⃣ **Pehle Learning par Focus Karo:**\n"
                "Tumhari age me sabse best investment hai knowledge me.\n\n"
                "2️⃣ **Paper Trading se Start Karo:**\n"
                "Virtual money se practice karo, risk ke bina strategies seekho.\n\n"
                "3️⃣ **Basics Strong Karo:**\n"
                "Markets, technical analysis, risk management samjho.\n\n"
                "4️⃣ **Strong Foundation Banao:**\n"
                "Real money se pehle education par focus karo.",
                reply_markup=keyboard,
                delay=1.5
            )
            
            await asyncio.sleep(2.0)
            
            await slow_send_message(
                update, context,
                f"{personalized_msg}, tum perfect age pe ho learning start karne ke liye! 🎓\n\n"
                "Hamare channels join karo free educational content ke liye:\n"
                "- Daily market analysis\n"
                "- Trading strategies\n"
                "- Risk management tips\n"
                "- Paper trading exercises\n\n"
                "Pehle skills build karo, jab 18+ ho jaoge, tab ready rahoge! 💪",
                delay=1.5
            )
            
            await asyncio.sleep(2.0)
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Haan, main seekhna chahta hoon", callback_data='underage_learn'),
                    InlineKeyboardButton("❌ Abhi nahi, baad mein", callback_data='underage_later')
                ]
            ])
            
            await slow_send_message(
                update, context,
                f"{personalized_msg}, kya tum free educational content ke saath continue karna chahte ho\n"
                "aur trading properly seekhna chahte ho real money use karne se pehle?",
                reply_markup=keyboard,
                delay=1.0
            )
            
            session.update_state(WAITING_FOR_UNDERAGE_RESPONSE)
            return WAITING_FOR_UNDERAGE_RESPONSE
        else:
            # User is 18 or older
            session.age = age_text
            session.add_to_history(f"Age: {age_text} (18+)", is_user=True)
            
            logger.info(f"User {user_id} age: {age_text} (18+)")
            
            # Update state to ask about trading account
            session.update_state(WAITING_FOR_ACCOUNT_STATUS)
            
            personalized_msg = "bro"
            if session.name:
                personalized_msg = session.name
            
            await asyncio.sleep(0.8)
            await slow_send_message(
                update, context,
                f"Perfect {personalized_msg}! {age_text} years trading start karne ke liye perfect age hai! 👍",
                delay=1.0
            )
            
            await asyncio.sleep(1.5)
            
            # Ask about existing trading account
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Haan, Already Account Hai", callback_data='account_yes'),
                    InlineKeyboardButton("❌ Nahi, Account Nahi Hai", callback_data='account_no')
                ]
            ])
            
            await slow_send_message(
                update, context,
                f"{personalized_msg}, kya tumhara already koi trading account hai?",
                reply_markup=keyboard,
                delay=1.0
            )
            
            return WAITING_FOR_ACCOUNT_STATUS
            
    except ValueError:
        # If age is not a number, just store it and continue
        session.age = age_text
        session.add_to_history(f"Age: {age_text}", is_user=True)
        
        logger.info(f"User {user_id} age: {age_text}")
        
        # Update state
        session.update_state(WAITING_FOR_EXPERIENCE)
        
        personalized_msg = "bro"
        if session.name:
            personalized_msg = session.name
        
        await asyncio.sleep(0.8)
        await slow_send_message(
            update, context,
            f"Got it {personalized_msg}! Trading start karne ke liye perfect! 👍",
            delay=1.0
        )
        
        # Ask experience question with delay
        await asyncio.sleep(1.5)
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("❌ No, bilkul beginner hoon", callback_data='exp_no'),
                InlineKeyboardButton("✅ Haan, thoda bahut aata hai", callback_data='exp_yes')
            ]
        ])
        
        await slow_send_message(
            update, context,
            f"{personalized_msg}, kya tumhe pehle trading ka thoda bhi experience hai?",
            reply_markup=keyboard,
            delay=1.0
        )
        
        return WAITING_FOR_EXPERIENCE

async def handle_account_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle trading account status."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    session = get_user_session(user_id)
    
    personalized_msg = "bro"
    if session.name:
        personalized_msg = session.name
    
    if query.data == 'account_yes':
        # User has existing account
        session.has_trading_account = True
        
        await query.edit_message_text(
            f"Accha {personalized_msg}, tumhara already account hai. ✅\n\n"
            f"Is account ko mere link se banaya hai ya kisi aur link se?"
        )
        
        await asyncio.sleep(1.5)
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Haan, Aapki Link Se Hai", callback_data='account_with_link'),
                InlineKeyboardButton("❌ Nahi, Dusri Link Se Hai", callback_data='account_without_link')
            ]
        ])
        
        await slow_send_message(
            update, context,
            f"{personalized_msg}, kya yeh account meri link se banaya hai?",
            reply_markup=keyboard,
            delay=1.0
        )
        
        return WAITING_FOR_ACCOUNT_STATUS
        
    else:  # account_no
        # User doesn't have account
        session.has_trading_account = False
        
        await query.edit_message_text(
            f"Accha {personalized_msg}, koi baat nahi! Hum new account banayenge. ✅"
        )
        
        # Send registration instructions
        await asyncio.sleep(1.5)
        return await send_registration_instructions(update, context, session)

async def handle_account_link_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle if account was created with our link."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    session = get_user_session(user_id)
    
    personalized_msg = "bro"
    if session.name:
        personalized_msg = session.name
    
    if query.data == 'account_with_link':
        # Account created with our link
        session.account_created_with_link = True
        
        await query.edit_message_text(
            f"Bht achi baat h bhai {personalized_msg}! 👍\n\n"
            f"Aap apni trader ID bhej do.\n\n"
            "Trader ID find karne ka tareeka:\n"
            "1. Pocket Option app ya website open karo\n"
            "2. Profile section mein jao\n"
            "3. Wahan tumhara Trader ID dikhega\n"
            "4. Us ID ko yahan send karo\n\n"
            "Format: 12345678 (Only Numeric Digit Allowed)"
        )
        
        session.update_state(WAITING_FOR_TRADER_ID)
        return WAITING_FOR_TRADER_ID
        
    else:  # account_without_link
        # Account created with other link
        session.account_created_with_link = False
        
        await query.edit_message_text(
            f"{personalized_msg}, agar tumhara account meri link se nahi hai, toh kuch issues ho sakte hain:"
        )
        
        await asyncio.sleep(1.5)
        
        # Send important warning message
        warning_message = (
            "⚠️ **IMPORTANT NOTICE** ⚠️\n\n"
            "✅ AGAR APKA ACCOUNT MERI LINK SE NAHI HAI\n\n"
            "✅ DELETE YOUR OLD ACCOUNT AND CREATE NEW POCKET OPTION ACCOUNT WITH MY LINK\n"
            "USE NEW EMAIL\n\n"
            "✅ NO PROBLEM AGAIN VERIFY WITH SAME DOCUMENTS\n\n"
            "✅ CREATE POCKET OPTION ACCOUNT THROUGH THIS LINK -\n"
            f"🔗 {config.TRADING_LINK}\n\n"
            "🍃 DEPOSIT 150$ with Bonus\n\n"
            "SEND TRADER ID HERE\n\n"
            "Kyun zaroori hai?\n"
            "• Proper tracking ke liye\n"
            "• Bonuses aur benefits ke liye\n"
            "• Personal guidance ke liye\n"
            "• Support system ke liye"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ CREATE NEW ACCOUNT", url=config.TRADING_LINK)]
        ])
        
        await slow_send_message(
            update, context,
            warning_message,
            reply_markup=keyboard,
            delay=1.5
        )
        
        await asyncio.sleep(2.0)
        
        await slow_send_message(
            update, context,
            f"{personalized_msg}, new account create karne ke baad mujhe TRADER ID yahan send karna.\n\n"
            "Trader ID find karne ka tareeka:\n"
            "1. Pocket Option app ya website open karo\n"
            "2. Profile section mein jao\n"
            "3. Wahan tumhara Trader ID dikhega\n"
            "4. Us ID ko yahan send karo",
            delay=1.5
        )
        
        session.update_state(WAITING_FOR_TRADER_ID)
        return WAITING_FOR_TRADER_ID

async def handle_trader_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle trader ID submission and send to admin for approval."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    
    trader_id = update.message.text.strip()
    
    # Validate trader ID: must be exactly 8 digits
    if not trader_id.isdigit() or len(trader_id) != 8:
        await slow_send_message(
            update, context,
            "❌ Aapko sirf trader id 8 digit ki daalni h.\n"
            "Eg- 12345678\n\n"
            "Kripya apni 8 digit trader ID dobara send karein.",
            delay=1.0
        )
        return WAITING_FOR_TRADER_ID
    
    session.trader_id = trader_id
    session.add_to_history(f"Trader ID: {trader_id}", is_user=True)
    
    logger.info(f"User {user_id} submitted trader ID: {trader_id}")
    
    personalized_msg = "bro"
    if session.name:
        personalized_msg = session.name
    
    # Valid trader ID
    if len(trader_id) == 8:
        await slow_send_message(
            update, context,
            f"Perfect {personalized_msg}! ✅\n"
            f"Trader ID received: {trader_id}\n\n"
            "Main isko verify karta hoon aur tumhare account details check karta hoon.\n"
            "Thoda wait karo... ⏳",
            delay=1.0
        )
        
        # Store pending verification
        pending_verifications[user_id] = {
            'trader_id': trader_id,
            'name': session.name,
            'age': session.age,
            'has_account': session.has_trading_account,
            'created_with_link': session.account_created_with_link,
            'username': update.effective_user.username,
            'timestamp': datetime.now()
        }
        
        # Escape special characters for HTML
        def escape_html(text):
            if text is None:
                return "Not provided"
            return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        # Prepare safe values for HTML
        safe_name = escape_html(session.name) if session.name else "Not provided"
        safe_username = escape_html(update.effective_user.username) if update.effective_user.username else "No username"
        safe_age = escape_html(session.age) if session.age else "Not provided"
        
        # Send to admin for approval (using HTML format)
        admin_msg = (
            f"🆕 <b>New Trader ID Verification Request</b>\n\n"
            f"👤 <b>User Details:</b>\n"
            f"• User ID: <code>{user_id}</code>\n"
            f"• Name: {safe_name}\n"
            f"• Username: @{safe_username}\n"
            f"• Age: {safe_age}\n\n"
            f"📊 <b>Trading Details:</b>\n"
            f"• Trader ID: <code>{trader_id}</code>\n"
            f"• Has Account: {'Yes' if session.has_trading_account else 'No'}\n"
            f"• Created with Link: {'Yes' if session.account_created_with_link else 'No/New Account'}\n\n"
            f"⏰ Time: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Allow & Continue", callback_data=f"approve_{user_id}"),
                InlineKeyboardButton("❌ Deny", callback_data=f"deny_{user_id}")
            ],
            [
                InlineKeyboardButton("🔄 Partially Allow", callback_data=f"partial_{user_id}")
            ]
        ])
        
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_msg,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
            logger.info(f"Sent verification request to admin for user {user_id}")
            
            # Send waiting message to user
            await asyncio.sleep(1)
            await slow_send_message(
                update, context,
                f"{personalized_msg}, tumhara verification request admin ko bhej diya gaya hai. ✅\n\n"
                "Admin approval ka wait karo. Jald hi response milega! ⏳",
                delay=1.0
            )
            
        except Exception as e:
            logger.error(f"Error sending to admin: {e}")
            await slow_send_message(
                update, context,
                f"{personalized_msg}, verification request bhejtey samay technical issue aa gaya. 😔\n\n"
                "Please thodi der baad apna Trader ID dobara bhejo.",
                delay=1.0
            )
            return WAITING_FOR_TRADER_ID
        
        session.update_state(WAITING_FOR_ADMIN_APPROVAL)
        return WAITING_FOR_ADMIN_APPROVAL
        
    else:
        await slow_send_message(
            update, context,
            f"{personalized_msg}, yeh sahi Trader ID nahi lag raha. Please check karo:\n\n"
            "1. Pocket Option app ya website pe profile section mein jao\n"
            "2. Trader ID wahan clearly dikhega\n"
            "3. Woh ID yahan bhejo (only numbers allowed)\n\n"
            "Example: 12345678 (Only Numeric Digit Allowed)",
            delay=1.0
        )
        
        # Stay in same state to get correct ID
        return WAITING_FOR_TRADER_ID

async def send_registration_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE, session: UserSession) -> int:
    """Send registration instructions for new users."""
    personalized_msg = "bro"
    if session.name:
        personalized_msg = session.name
    
    reg_msg = (
        f"{personalized_msg}, ab hum new account banayenge. Follow these steps carefully: 👇\n\n"
        "✅ CREATE POCKET OPTION ACCOUNT THROUGH THIS LINK -\n"
        f"🔗 {config.TRADING_LINK}\n\n"
        "Important Points:\n"
        "✔ VPN OFF hona chahiye\n"
        "✔ Web version use karna better hai\n"
        "✔ New email use karna\n"
        "✔ Same documents se verify kar sakte ho\n\n"
        "🍃 DEPOSIT 150$ with Bonus"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ CREATE ACCOUNT", url=config.TRADING_LINK)]
    ])
    
    await slow_send_message(
        update, context,
        reg_msg,
        reply_markup=keyboard,
        delay=1.5
    )
    
    await asyncio.sleep(1.5)
    
    await slow_send_message(
        update, context,
        f"{personalized_msg}, account create karne ke baad mujhe TRADER ID yahan send karna.\n\n"
        "Trader ID find karne ka tareeka:\n"
        "1. Pocket Option app ya website open karo\n"
        "2. Profile section mein jao\n"
        "3. Wahan tumhara Trader ID dikhega\n"
        "4. Us ID ko yahan send karo\n\n"
        "Format: 12345678 (Only Numeric Digit Allowed)",
        delay=1.5
    )
    
    session.update_state(WAITING_FOR_TRADER_ID)
    return WAITING_FOR_TRADER_ID

async def handle_underage_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle response from underage users."""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'underage_learn':
        await asyncio.sleep(1.0)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎥 YouTube Learning Playlist", url=config.YOUTUBE_CHANNEL)],
            [InlineKeyboardButton("📚 Telegram Education Channel", url=config.TELEGRAM_CHANNEL)],
            [InlineKeyboardButton("📊 Paper Trading Apps", callback_data='paper_trading_info')]
        ])
        
        await slow_send_message(
            update, context,
            "Badhiya decision hai! 🎓\n\n"
            "**Tumhare Liye Free Learning Path:**\n\n"
            "📅 **Week 1-2:** Markets ki Basics\n"
            "• Stocks/Forex/Crypto kya hain\n"
            "• Markets kaise kaam karte hain\n"
            "• Basic terminology\n\n"
            "📅 **Week 3-4:** Technical Analysis\n"
            "• Candlestick patterns\n"
            "• Support & Resistance\n"
            "• Indicators ki basics\n\n"
            "📅 **Month 2:** Paper Trading\n"
            "• Virtual money se practice\n"
            "• Risk-free strategies test karo\n"
            "• Confidence build karo\n\n"
            "📅 **Month 3+:** Advanced Concepts\n"
            "• Risk management\n"
            "• Trading psychology\n"
            "• Portfolio building",
            reply_markup=keyboard,
            delay=1.5
        )
        
        await asyncio.sleep(2.0)
        
        await slow_send_message(
            update, context,
            "**Recommended Paper Trading Apps:**\n"
            "• TradingView (Paper Trading)\n"
            "• Investopedia Simulator\n"
            "• MetaTrader Demo Account\n\n"
            "₹1 lakh virtual money se start karo aur practice karo!\n\n"
            "Yaad rakhna: Best traders woh hain jo pehle years learning me spend karte hain. 💡",
            delay=1.5
        )
        
        await asyncio.sleep(1.5)
        
        await slow_send_message(
            update, context,
            "Main tumhe periodic educational content bhejunga aur tumhari learning progress check karta rahunga! 📚\n\n"
            "Learning materials review karne ke liye kabhi bhi /start type karna.\n\n"
            "Keep learning! Market tumhara wait karegi. 🚀",
            delay=1.0
        )
        
    else:
        await slow_send_message(
            update, context,
            "Koi baat nahi! Jab bhi seekhna chahte ho, bas /start type karna.\n\n"
            "Yaad rakhna: Tumhari age me knowledge sabse best investment hai. 📖\n\n"
            "All the best for your studies! 👍",
            delay=1.0
        )
    
    return ConversationHandler.END

async def handle_paper_trading_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provide detailed paper trading information."""
    query = update.callback_query
    await query.answer()
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 YouTube Tutorials", url=config.YOUTUBE_CHANNEL)],
        [InlineKeyboardButton("💬 Telegram Community", url=config.TELEGRAM_CHANNEL)]
    ])
    
    await slow_send_message(
        update, context,
        "**📊 Paper Trading - Risk-Free Seekhne ka Best Tareeka:**\n\n"
        "✅ **Paper Trading Kya Hai?**\n"
        "• Virtual money se trading\n"
        "• Real market conditions\n"
        "• Financial risk zero\n\n"
        "✅ **Benefits:**\n"
        "1. Bina paisa lose kiye seekho\n"
        "2. Different strategies test karo\n"
        "3. Apne emotions samjho\n"
        "4. Confidence build karo\n\n"
        "✅ **Kaise Start Karein:**\n"
        "1. Paper trading platform choose karo\n"
        "2. ₹50,000-1,00,000 virtual money se start\n"
        "3. Real money ki tarah trade karo\n"
        "4. Apna performance track karo\n"
        "5. Mistakes se seekho\n\n"
        "✅ **Recommended Platforms:**\n"
        "• TradingView Paper Trading\n"
        "• Investopedia Simulator\n"
        "• MetaTrader 4/5 Demo\n"
        "• Zerodha Varsity\n\n"
        "**Yaad Rakho:** Real money se pehle 6-12 months paper trading karo!",
        reply_markup=keyboard,
        delay=1.5
    )

# ==============================
# WEEKLY SUMMARY SYSTEM
# ==============================
async def send_weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    """Send weekly summary to users."""
    current_time = datetime.now()
    
    # Check if it's Monday (start of week)
    if current_time.weekday() == 0:  # Monday is 0
        for user_id, session in list(user_sessions.items()):
            try:
                if session.registration_time and not session.is_underage:
                    if session.trading_days > 0:
                        personalized_msg = "bro"
                        if session.name:
                            personalized_msg = session.name
                        
                        summary_message = (
                            f"📊 **Weekly Trading Summary** 📊\n\n"
                            f"Hello {personalized_msg}! Yeh rahi last week ki summary:\n\n"
                            f"• Trading Days: {session.trading_days}\n"
                        )
                        
                        if session.total_profits > 0:
                            summary_message += f"• Total Profits: ₹{session.total_profits:,.2f}\n"
                        
                        if session.total_losses > 0:
                            summary_message += f"• Total Losses: ₹{session.total_losses:,.2f}\n"
                        
                        if session.total_profits > 0 or session.total_losses > 0:
                            net = session.total_profits - session.total_losses
                            if net > 0:
                                summary_message += f"• Net Profit: ₹{net:,.2f} 🎉\n"
                            elif net < 0:
                                summary_message += f"• Net Loss: ₹{abs(net):,.2f} 📉\n"
                            else:
                                summary_message += "• Break-even! 🤝\n"
                        
                        summary_message += "\n**Next Week Goals:**\n"
                        summary_message += "1. Consistency maintain karo\n"
                        summary_message += "2. Risk management follow karo\n"
                        summary_message += "3. Trading journal update karo\n"
                        summary_message += "4. Ek nayi strategy seekho\n\n"
                        summary_message += "Keep going! You're doing great! 💪"
                        
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=summary_message
                        )
                        
                        # Reset weekly stats (keep total for overall tracking)
                        session.trading_days = 0
                        session.total_profits = 0
                        session.total_losses = 0
                        
            except Exception as e:
                logger.error(f"Error sending weekly summary to user {user_id}: {e}")
                continue

# ==============================
# GENERAL MESSAGE HANDLER (GEMINI AI)
# ==============================
async def handle_trader_id_outside_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle trader ID submissions for users waiting after partial approval, or pass to general message handler."""
    try:
        user_id = update.effective_user.id
        
        # Skip for admin
        if user_id == ADMIN_ID:
            return
        
        session = get_user_session(user_id)
        
        # Check if user is in WAITING_FOR_TRADER_ID state (after partial approval)
        if session.state == WAITING_FOR_TRADER_ID:
            # This is a trader ID submission - handle it
            await handle_trader_id(update, context)
            return
        
        # Otherwise, pass to general message handler (Gemini AI)
        await handle_general_message(update, context)
        
    except Exception as e:
        logger.error(f"Error in handle_trader_id_outside_conv: {e}")
        await update.message.reply_text(
            "Sorry bro, kuch technical issue ho gaya. Thodi der baad try karna ya /start command use karna."
        )

async def handle_general_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle general messages using Gemini AI."""
    try:
        user_id = update.effective_user.id
        
        # Skip AI responses for admin (admin uses commands)
        if user_id == ADMIN_ID:
            return
        
        session = get_user_session(user_id)
        user_message = update.message.text
        
        # Add user message to history
        session.add_to_history(user_message, is_user=True)
        
        # Build context from session
        context_info = ""
        if session.name:
            context_info += f"User name: {session.name}. "
        if session.is_underage:
            context_info += "User is underage (below 18), focus on education and paper trading. "
        if session.has_trading_account:
            context_info += "User has a trading account. "
        
        # Get response from Gemini
        ai_response = await get_gemini_response(user_message, context_info)
        
        # Send response
        await slow_send_message(
            update, context,
            ai_response,
            delay=1.0
        )
        
    except Exception as e:
        logger.error(f"Error in handle_general_message: {e}")
        await update.message.reply_text(
            "Sorry bro, kuch technical issue ho gaya. Thodi der baad try karna ya /start command use karna."
        )

# ==============================
# ADMIN PANEL FUNCTIONS
# ==============================
async def approve_trader_id(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, custom_message: str = None) -> int:
    """Approve trader ID and send success message with guidance."""
    if user_id not in pending_verifications:
        return ConversationHandler.END
    
    verification_data = pending_verifications[user_id]
    session = get_user_session(user_id)
    
    personalized_msg = "bro"
    if verification_data['name']:
        personalized_msg = verification_data['name']
    
    try:
        # Send approval message to user
        approval_text = (
            f"✅ **Verification Complete!**\n\n"
            f"{personalized_msg}, tumhara account successfully verify ho gaya hai! 🎉\n\n"
            f"Ab main tumhe next steps personally guide karunga."
        )
        
        await context.bot.send_message(
            chat_id=user_id,
            text=approval_text
        )
        
        # Send custom message if provided
        if custom_message:
            await asyncio.sleep(1)
            await context.bot.send_message(
                chat_id=user_id,
                text=custom_message
            )
        
        await asyncio.sleep(1.5)
        
        # Send daily timetable guidance
        timetable_msg = (
            f"📅 **Daily Trading Timetable & Guidance:**\n\n"
            f"**Morning Routine (8:00 AM - 10:00 AM):**\n"
            f"• Market analysis karo\n"
            f"• News check karo\n"
            f"• Trading plan banao\n\n"
            f"**Trading Session 1 (10:00 AM - 12:00 PM):**\n"
            f"• Morning trades execute karo\n"
            f"• 1-2% risk per trade\n"
            f"• Stop loss zaroor lagao\n\n"
            f"**Mid-Day (12:00 PM - 2:00 PM):**\n"
            f"• Break lelo\n"
            f"• Morning trades ka review karo\n"
            f"• Afternoon strategy prepare karo\n\n"
            f"**Trading Session 2 (2:00 PM - 4:00 PM):**\n"
            f"• Afternoon trades\n"
            f"• Market trends follow karo\n"
            f"• Profit booking karo\n\n"
            f"**Evening Review (6:00 PM - 7:00 PM):**\n"
            f"• Trading journal update karo\n"
            f"• P&L calculate karo\n"
            f"• Next day ka plan banao\n\n"
            f"**Important Rules:**\n"
            f"✅ Daily maximum 3-5 trades\n"
            f"✅ Risk only 1-2% per trade\n"
            f"✅ Follow stop loss strictly\n"
            f"✅ Don't overtrade\n"
            f"✅ Keep emotions in control"
        )
        
        await context.bot.send_message(
            chat_id=user_id,
            text=timetable_msg
        )
        
        await asyncio.sleep(2)
        
        # Send daily motivation
        motivation_msg = (
            f"💪 **Daily Motivation & Tips:**\n\n"
            f"{random.choice(MOTIVATIONAL_MESSAGES)}\n\n"
            f"**Remember:**\n"
            f"📈 Consistency is the key to success\n"
            f"🧠 Control your emotions\n"
            f"💰 Protect your capital first\n"
            f"📚 Keep learning every day\n"
            f"⏰ Be patient with the market\n\n"
            f"Main daily tumhare saath rahunga. Any doubts ho toh message karna! 🚀"
        )
        
        await context.bot.send_message(
            chat_id=user_id,
            text=motivation_msg
        )
        
        # Store registration time
        session.registration_time = datetime.now()
        session.last_checkin = session.registration_time
        session.update_state(START)
        
        # Remove from pending
        del pending_verifications[user_id]
        
        logger.info(f"User {user_id} approved and guidance sent")
        
    except Exception as e:
        logger.error(f"Error sending approval to user {user_id}: {e}")
    
    return ConversationHandler.END

async def handle_admin_reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin's custom message for approval."""
    if update.effective_user.id != ADMIN_ID:
        return
    
    # Check if admin is awaiting to send a reply
    if ADMIN_ID not in admin_awaiting_reply:
        return  # Not waiting for admin reply, let other handlers process
    
    custom_message = update.message.text.strip()
    user_data = admin_awaiting_reply[ADMIN_ID]
    user_id = user_data.get('user_id')
    
    if not user_id:
        await update.message.reply_text("❌ Error: No pending approval found.")
        del admin_awaiting_reply[ADMIN_ID]
        return
    
    # Approve with custom message
    await approve_trader_id(update, context, user_id, custom_message)
    
    await update.message.reply_text(
        f"✅ <b>User {user_id} has been approved!</b>\n\n"
        f"Your custom message has been sent to the user.",
        parse_mode='HTML'
    )
    
    # Clear the stored data
    del admin_awaiting_reply[ADMIN_ID]

async def deny_trader_id(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> int:
    """Deny trader ID and ask user to create account with link."""
    if user_id not in pending_verifications:
        return ConversationHandler.END
    
    verification_data = pending_verifications[user_id]
    session = get_user_session(user_id)
    
    personalized_msg = "bro"
    if verification_data['name']:
        personalized_msg = verification_data['name']
    
    try:
        # Send denial message
        denial_msg = (
            f"{personalized_msg}, lagta h aapka account hmare link se nahi bana hai.\n\n"
            f"Koi baat nahi hum naya account banayenge.\n\n"
            f"✅ DELETE YOUR OLD ACCOUNT AND CREATE NEW POCKET OPTION ACCOUNT WITH MY LINK\n"
            f"USE NEW EMAIL\n\n"
            f"✅ NO PROBLEM AGAIN VERIFY WITH SAME DOCUMENTS\n\n"
            f"✅ CREATE POCKET OPTION ACCOUNT THROUGH THIS LINK -\n"
            f"🔗 {config.TRADING_LINK}\n\n"
            f"🍃 DEPOSIT 150$ with Bonus\n\n"
            f"SEND TRADER ID HERE"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ CREATE ACCOUNT", url=config.TRADING_LINK)]
        ])
        
        await context.bot.send_message(
            chat_id=user_id,
            text=denial_msg,
            reply_markup=keyboard
        )
        
        # Reset to trader ID state
        session.update_state(WAITING_FOR_TRADER_ID)
        
        # Remove from pending
        del pending_verifications[user_id]
        
        logger.info(f"User {user_id} denied verification")
        
    except Exception as e:
        logger.error(f"Error sending denial to user {user_id}: {e}")
    
    return WAITING_FOR_TRADER_ID

async def handle_message_during_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle messages when user is in WAITING_FOR_ADMIN_APPROVAL state.
    
    This handles the case when admin clicked 'Partially Allow' and user sends trader ID again.
    """
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    
    # Check if user's session state is WAITING_FOR_TRADER_ID (after partial approval)
    if session.state == WAITING_FOR_TRADER_ID:
        # User is supposed to send trader ID after partial approval
        return await handle_trader_id(update, context)
    
    # Otherwise, user is still waiting for admin approval - send reminder
    personalized_msg = "bro"
    if session.name:
        personalized_msg = session.name
    
    await slow_send_message(
        update, context,
        f"{personalized_msg}, tumhara verification request admin ke paas hai. ⏳\n\n"
        "Thoda wait karo, jald hi approval mil jayega! 🚀",
        delay=1.0
    )
    
    return WAITING_FOR_ADMIN_APPROVAL

async def partially_allow_trader_id(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> int:
    """Partially allow trader ID and ask user to complete account setup and send trader ID again."""
    if user_id not in pending_verifications:
        return ConversationHandler.END
    
    verification_data = pending_verifications[user_id]
    session = get_user_session(user_id)
    
    personalized_msg = "bro"
    if verification_data['name']:
        personalized_msg = verification_data['name']
    
    try:
        # Send partial approval message
        partial_msg = (
            f"Dekho {personalized_msg},\n\n"
            f"Aapne id create kar li hai\n"
            f"Ab bas apko deposit karna hai\n"
            f"Minimum aap 150$ add karlo\n\n"
            f"And send your trader id here."
        )
        
        await context.bot.send_message(
            chat_id=user_id,
            text=partial_msg
        )
        
        # Reset to trader ID state - user needs to send trader ID again
        session.update_state(WAITING_FOR_TRADER_ID)
        
        # Remove from pending - they will be added again when they send trader ID
        del pending_verifications[user_id]
        
        logger.info(f"User {user_id} partially allowed, waiting for trader ID again")
        
    except Exception as e:
        logger.error(f"Error sending partial approval to user {user_id}: {e}")
    
    return WAITING_FOR_TRADER_ID

async def handle_admin_verification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin approval/denial/partial callback."""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Unauthorized!", show_alert=True)
        return
    
    data = query.data
    action, user_id_str = data.split('_', 1)
    user_id = int(user_id_str)
    
    if action == 'approve':
        # Auto-approve without waiting for custom message
        await query.edit_message_text(
            query.message.text + "\n\n✅ <b>APPROVED</b>",
            parse_mode='HTML'
        )
        
        # Approve the user immediately
        await approve_trader_id(update, context, user_id, None)
        
    elif action == 'deny':
        await query.edit_message_text(
            query.message.text + "\n\n❌ <b>DENIED</b>",
            parse_mode='HTML'
        )
        await deny_trader_id(update, context, user_id)
        
    elif action == 'partial':
        await query.edit_message_text(
            query.message.text + "\n\n🔄 <b>PARTIALLY ALLOWED</b>",
            parse_mode='HTML'
        )
        await partially_allow_trader_id(update, context, user_id)

async def admin_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to broadcast text message to all users."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized access!")
        return
    
    # Format: /broadcast_text Your message here
    message_text = update.message.text.replace('/broadcast_text', '').strip()
    
    if not message_text:
        await update.message.reply_text(
            "Usage: /broadcast_text Your message here\n\n"
            "Example: /broadcast_text Hello everyone! Market update..."
        )
        return
    
    sent_count = 0
    failed_count = 0
    
    await update.message.reply_text(f"📢 Broadcasting to {len(user_sessions)} users...")
    
    for user_id, session in list(user_sessions.items()):
        try:
            if session.registration_time:  # Only send to registered users
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message_text
                )
                sent_count += 1
                await asyncio.sleep(0.1)  # Avoid rate limiting
        except Exception as e:
            logger.error(f"Failed to send broadcast to {user_id}: {e}")
            failed_count += 1
    
    await update.message.reply_text(
        f"✅ Broadcast complete!\n\n"
        f"Sent: {sent_count}\n"
        f"Failed: {failed_count}"
    )

async def admin_broadcast_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin sends audio to broadcast to all users."""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not update.message.audio and not update.message.voice:
        return
    
    caption = update.message.caption or ""
    audio_file = update.message.audio or update.message.voice
    
    sent_count = 0
    failed_count = 0
    
    await update.message.reply_text(f"🎵 Broadcasting audio to {len(user_sessions)} users...")
    
    for user_id, session in list(user_sessions.items()):
        try:
            if session.registration_time:
                if update.message.audio:
                    await context.bot.send_audio(
                        chat_id=user_id,
                        audio=audio_file.file_id,
                        caption=caption if caption else None
                    )
                else:
                    await context.bot.send_voice(
                        chat_id=user_id,
                        voice=audio_file.file_id,
                        caption=caption if caption else None
                    )
                sent_count += 1
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Failed to send audio to {user_id}: {e}")
            failed_count += 1
    
    await update.message.reply_text(
        f"✅ Audio broadcast complete!\n\n"
        f"Sent: {sent_count}\n"
        f"Failed: {failed_count}"
    )

async def admin_broadcast_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin sends video to broadcast to all users."""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not update.message.video:
        return
    
    caption = update.message.caption or ""
    video_file = update.message.video
    
    sent_count = 0
    failed_count = 0
    
    await update.message.reply_text(f"🎥 Broadcasting video to {len(user_sessions)} users...")
    
    for user_id, session in list(user_sessions.items()):
        try:
            if session.registration_time:
                await context.bot.send_video(
                    chat_id=user_id,
                    video=video_file.file_id,
                    caption=caption if caption else None
                )
                sent_count += 1
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Failed to send video to {user_id}: {e}")
            failed_count += 1
    
    await update.message.reply_text(
        f"✅ Video broadcast complete!\n\n"
        f"Sent: {sent_count}\n"
        f"Failed: {failed_count}"
    )

async def admin_broadcast_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin sends photo to broadcast to all users."""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not update.message.photo:
        return
    
    caption = update.message.caption or ""
    photo_file = update.message.photo[-1]  # Get highest resolution
    
    sent_count = 0
    failed_count = 0
    
    await update.message.reply_text(f"📸 Broadcasting photo to {len(user_sessions)} users...")
    
    for user_id, session in list(user_sessions.items()):
        try:
            if session.registration_time:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo_file.file_id,
                    caption=caption if caption else None
                )
                sent_count += 1
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Failed to send photo to {user_id}: {e}")
            failed_count += 1
    
    await update.message.reply_text(
        f"✅ Photo broadcast complete!\n\n"
        f"Sent: {sent_count}\n"
        f"Failed: {failed_count}"
    )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin statistics."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized access!")
        return
    
    total_users = len(user_sessions)
    registered_users = sum(1 for s in user_sessions.values() if s.registration_time)
    underage_users = sum(1 for s in user_sessions.values() if s.is_underage)
    pending_approvals = len(pending_verifications)
    
    stats_msg = (
        f"📊 **Bot Statistics:**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"✅ Registered Users: {registered_users}\n"
        f"🔞 Underage Users: {underage_users}\n"
        f"⏳ Pending Approvals: {pending_approvals}\n\n"
        f"**Admin Commands:**\n"
        f"/broadcast_text <message> - Send text to all\n"
        f"Send audio/voice - Auto-broadcast\n"
        f"Send video - Auto-broadcast\n"
        f"/stats - Show these statistics\n"
        f"/pending - Show pending verifications"
    )
    
    await update.message.reply_text(stats_msg)

async def admin_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show pending verifications."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized access!")
        return
    
    if not pending_verifications:
        await update.message.reply_text("✅ No pending verifications!")
        return
    
    msg = "⏳ **Pending Verifications:**\n\n"
    
    for user_id, data in pending_verifications.items():
        msg += (
            f"User ID: {user_id}\n"
            f"Name: {data['name']}\n"
            f"Trader ID: {data['trader_id']}\n"
            f"Time: {data['timestamp'].strftime('%H:%M:%S')}\n"
            f"---\n"
        )
    
    await update.message.reply_text(msg)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin panel menu."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized access!")
        return
    
    panel_msg = (
        "🔐 <b>ADMIN PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📊 <b>Statistics:</b>\n"
        f"• Total Users: {len(user_sessions)}\n"
        f"• Registered: {sum(1 for s in user_sessions.values() if s.registration_time)}\n"
        f"• Pending Approvals: {len(pending_verifications)}\n\n"
        "📢 <b>Broadcast Commands:</b>\n\n"
        "📝 <b>Text Broadcast:</b>\n"
        "<code>/broadcast_text Your message here</code>\n"
        "Example: <code>/broadcast_text Market update...</code>\n\n"
        "🎵 <b>Audio Broadcast:</b>\n"
        "Simply send an audio or voice message\n"
        "It will auto-broadcast to all users\n\n"
        "🎥 <b>Video Broadcast:</b>\n"
        "Simply send a video message\n"
        "It will auto-broadcast to all users\n\n"
        "⚙️ <b>Management Commands:</b>\n"
        "<code>/stats</code> - View detailed statistics\n"
        "<code>/pending</code> - View pending verifications\n"
        "<code>/admin</code> - Show this panel\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <b>Tips:</b>\n"
        "• Trader ID approvals appear automatically\n"
        "• Use Approve/Deny buttons for verification\n"
        "• All broadcasts go to registered users only"
    )
    
    await update.message.reply_text(panel_msg, parse_mode='HTML')

# ==============================
# CANCEL HANDLER
# ==============================
async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the /cancel command to exit conversation."""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    
    await update.message.reply_text(
        "Process cancelled. Koi baat nahi! 😊\n\n"
        "Jab bhi phir se start karna ho, bas /start type karna.",
    )
    
    # Reset session state
    session.update_state(START)
    
    return ConversationHandler.END

# ==============================
# MAIN APPLICATION SETUP
# ==============================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors caused by Updates."""
    logger.error(f"Exception while handling an update: {context.error}")
    
    # Handle SSL errors gracefully - just log and continue
    if "SSL" in str(context.error) or "CERTIFICATE" in str(context.error):
        logger.warning("SSL error occurred, but continuing...")
        return
    
    # For other network errors, log and continue
    if isinstance(context.error, NetworkError):
        logger.warning(f"Network error: {context.error}")
        return

def main():
    """Start the bot with all features."""
    
    # Validate configuration
    if not config.validate_urls():
        logger.warning("Some URLs are invalid. Buttons may not work.")
    
    TOKEN = "8385950687:AAGdAqF6ZvvVZmJ79kwhJIdCfLXfJnKzVJw"  # Your actual token
    
    # Set SSL certificate path using certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
    
    # Create custom request
    request = HTTPXRequest(
        http_version="1.1",
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )
    
    # Create application with custom request
    application = (
        Application.builder()
        .token(TOKEN)
        .request(request)
        .build()
    )
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Add periodic jobs
    job_queue = application.job_queue
    if job_queue:
        # Daily follow-up at 9:30 AM
        job_queue.run_daily(
            send_daily_followup,
            time=datetime.strptime("09:30", "%H:%M").time(),
            days=(0, 1, 2, 3, 4, 5, 6)  # All days
        )
        
        # Periodic check-ins every 30 minutes
        job_queue.run_repeating(
            periodic_checkin,
            interval=1800,  # 30 minutes
            first=10
        )
        
        # Inactivity reminders every 5 minutes
        job_queue.run_repeating(
            send_inactivity_reminders,
            interval=300,  # 5 minutes (checks every 5 min, sends at 10 and 30)
            first=60  # Start after 1 minute
        )
        
        # Weekly summary on Monday at 10 AM
        job_queue.run_daily(
            send_weekly_summary,
            time=datetime.strptime("10:00", "%H:%M").time(),
            days=(0,)  # Monday only
        )
        
        logger.info("Daily follow-up system activated")
        logger.info("Weekly summary system activated")
        logger.info("Periodic checkin system activated")
    
    # Define conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            WAITING_FOR_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)
            ],
            WAITING_FOR_AGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_age)
            ],
            WAITING_FOR_ACCOUNT_STATUS: [
                CallbackQueryHandler(handle_account_link_status, pattern='^account_with_|^account_without_'),
                CallbackQueryHandler(handle_account_status, pattern='^account_(yes|no)$')
            ],
            WAITING_FOR_TRADER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_trader_id)
            ],
            WAITING_FOR_UNDERAGE_RESPONSE: [
                CallbackQueryHandler(handle_underage_response, pattern='^underage_')
            ],
            WAITING_PROFIT_LOSS: [
                CallbackQueryHandler(handle_daily_response, pattern='^daily_')
            ],
            WAITING_FOR_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount_response)
            ],
            WAITING_FOR_ADMIN_APPROVAL: [
                # Handle text messages - user might send trader ID after partial approval
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_during_approval)
            ]
        },
        fallbacks=[CommandHandler('cancel', handle_cancel)],
        allow_reentry=True,
        per_user=True,
        per_chat=True
    )
    
    # Add conversation handler FIRST
    application.add_handler(conv_handler)
    
    # Add admin reply handler (only when waiting for admin reply)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.User(ADMIN_ID),
        handle_admin_reply_message
    ))
    
    # Add admin handlers
    application.add_handler(CommandHandler('admin', admin_panel))
    application.add_handler(CommandHandler('broadcast_text', admin_broadcast_text))
    application.add_handler(CommandHandler('stats', admin_stats))
    application.add_handler(CommandHandler('pending', admin_pending))
    application.add_handler(MessageHandler(
        filters.AUDIO & filters.User(ADMIN_ID),
        admin_broadcast_audio
    ))
    application.add_handler(MessageHandler(
        filters.VOICE & filters.User(ADMIN_ID),
        admin_broadcast_audio
    ))
    application.add_handler(MessageHandler(
        filters.VIDEO & filters.User(ADMIN_ID),
        admin_broadcast_video
    ))
    application.add_handler(MessageHandler(
        filters.PHOTO & filters.User(ADMIN_ID),
        admin_broadcast_photo
    ))
    
    # Add handler for admin verification callbacks
    application.add_handler(CallbackQueryHandler(
        handle_admin_verification,
        pattern='^(approve|deny|partial)_'
    ))
    
    # Add handler for daily responses
    application.add_handler(CallbackQueryHandler(
        handle_daily_response, 
        pattern='^daily_'
    ))
    
    # Add handler for paper trading info
    application.add_handler(CallbackQueryHandler(
        handle_paper_trading_info, 
        pattern='^paper_trading_info$'
    ))
    
    # Add handler for trader ID submissions (for users waiting after partial approval)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_trader_id_outside_conv
    ))
    
    logger.info("Bot starting with name collection and account verification system...")
    
    # Start polling with error handling
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            break  # If successful, exit loop
        except Exception as e:
            retry_count += 1
            logger.error(f"Error starting bot (attempt {retry_count}/{max_retries}): {e}")
            if retry_count < max_retries:
                logger.info(f"Retrying in 5 seconds...")
                import time
                time.sleep(5)
            else:
                logger.error("Failed to start bot after multiple attempts.")
                logger.error("Please check your internet connection and try again.")
                raise

if __name__ == '__main__':
    main()
