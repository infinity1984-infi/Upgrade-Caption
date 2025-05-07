import logging
import re
from telegram import Update, Sticker
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
    Request,
)
from config import BOT_TOKEN, DEFAULT_QUALITIES, DEFAULT_FORMAT, TIMEOUT_CONFIG

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
(SET_STICKER, SET_FORMAT, MODE, COUNT, VIDEOS, DETAILS) = range(6)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot is Alive!\n"
        "/setsticker – Reply to a sticker to register it\n"
        "/setformat – Override caption template\n"
        "/forepisode – 3 videos single episode\n"
        "/forseason – full season (3×N videos)\n"
        "/forspecificquality – one video per episode at chosen quality\n"
        "/formarge – merge separate 480p/720p/1080p lists\n"
        "/cancel – Abort current operation"
    )
    return MODE

async def set_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message or not msg.reply_to_message.sticker:
        await msg.reply_text("❌ Reply to a sticker with /setsticker.")
        return SET_STICKER
    context.chat_data["sticker"] = msg.reply_to_message.sticker.file_id
    await msg.reply_text("✅ Sticker saved!")
    return ConversationHandler.END

async def set_format_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(
            "❌ Usage: /setformat <HTML with {title},{season},{episode},{quality}>"
        )
        return SET_FORMAT
    tpl = parts[1].strip()
    for ph in ("{title}", "{season}", "{episode}", "{quality}"):
        if ph not in tpl:
            await update.message.reply_text(f"❌ Missing placeholder {ph}.")
            return SET_FORMAT
    context.chat_data["format"] = tpl
    await update.message.reply_text("✅ Format updated!")
    return ConversationHandler.END

async def mode_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.split()[0].lower()
    context.user_data.clear()
    if cmd == "/forepisode":
        context.chat_data["mode"] = "EPISODE"
        await update.message.reply_text("📥 Send exactly 3 videos.")
        return VIDEOS
    if cmd == "/forseason":
        context.chat_data["mode"] = "SEASON"
        await update.message.reply_text("🔢 How many episodes?")
        return COUNT
    if cmd == "/forspecificquality":
        context.chat_data["mode"] = "SPECIFIC"
        await update.message.reply_text("🎚 Which quality? (e.g., 720p)")
        return COUNT
    if cmd == "/formarge":
        context.chat_data["mode"] = "MARGE"
        await update.message.reply_text("📊 How many episodes?")
        return COUNT
    await update.message.reply_text("❌ Unknown command. Use /start.")
    return ConversationHandler.END

async def receive_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    mode = context.chat_data["mode"]
    if mode == "SPECIFIC":
        context.chat_data["quality"] = txt
        await update.message.reply_text("🔢 How many episodes?")
        return COUNT
    if not txt.isdigit() or int(txt) < 1:
        await update.message.reply_text("❌ Send a positive integer.")
        return COUNT
    n = int(txt)
    context.chat_data["episodes"] = n
    context.chat_data["current"] = 1
    if mode in ("EPISODE", "SPECIFIC", "SEASON"):
        needed = 3 if mode == "EPISODE" else (n * 3 if mode == "SEASON" else n)
        await update.message.reply_text(f"📥 Send {needed} videos.")
        return VIDEOS
    # MARGE flow
    context.chat_data.setdefault("marge_lists", {"480p":[], "720p":[], "1080p":[]})
    context.chat_data["marge_stage"] = "480p"
    await update.message.reply_text(f"📥 Send all {n} videos in 480p.")
    return VIDEOS

async def receive_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vid = update.message.video or update.message.document
    if not vid or vid.mime_type.split("/")[0] != "video":
        await update.message.reply_text("❌ Please send a video file.")
        return VIDEOS
    mode = context.chat_data["mode"]
    if mode == "MARGE":
        stage = context.chat_data["marge_stage"]
        lst = context.chat_data["marge_lists"][stage]
        lst.append(vid.file_id)
        c = len(lst)
        await update.message.reply_text(f"✅ {stage} videos: {c}/{context.chat_data['episodes']}")
        if c >= context.chat_data["episodes"]:
            next_stage = {"480p":"720p", "720p":"1080p", "1080p":None}[stage]
            if next_stage:
                context.chat_data["marge_stage"] = next_stage
                await update.message.reply_text(f"📥 Now send all {context.chat_data['episodes']} videos in {next_stage}.")
                return VIDEOS
            await update.message.reply_text("📝 Now send details:\n1.Title\n2.Season")
            return DETAILS
        return VIDEOS
    # Other modes
    context.user_data.setdefault("videos", []).append(vid.file_id)
    cnt = len(context.user_data["videos"])
    mode = context.chat_data["mode"]
    needed = 3 if mode == "EPISODE" else (context.chat_data["episodes"] * 3 if mode == "SEASON" else context.chat_data["episodes"])
    await update.message.reply_text(f"✅ Received {cnt}/{needed} videos.")
    if cnt >= needed:
        await update.message.reply_text("📝 Now send details:\n1.Title\n2.Season")
        return DETAILS
    return VIDEOS

async def receive_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        lines = update.message.text.strip().splitlines()
        title = lines[0].strip()
        season = re.sub(r"\D", "", lines[1]).zfill(2)
        fmt = context.chat_data.get("format", DEFAULT_FORMAT)
        sticker = context.chat_data.get("sticker")
        mode = context.chat_data["mode"]
        videos = context.user_data.get("videos", [])
        qualities = context.chat_data.get("qualities", DEFAULT_QUALITIES)

        async def dispatch(ep, vids, qlist):
            await update.message.reply_text(f"<b>Episode {ep:02d} Added...!</b>", parse_mode="HTML")
            for i, v in enumerate(vids):
                q = qlist[i] if i < len(qlist) else qlist[-1]
                cap = fmt.format(title=title, season=season, episode=f"{ep:02d}", quality=q)
                await update.message.reply_video(video=v, caption=cap, parse_mode="HTML")
            if sticker:
                await update.message.reply_sticker(sticker=sticker)

        if mode == "EPISODE":
            await dispatch(1, videos[:3], qualities)
        elif mode == "SEASON":
            n = context.chat_data["episodes"]
            for ep in range(1, n+1):
                batch = videos[(ep-1)*3:ep*3]
                await dispatch(ep, batch, qualities)
        elif mode == "SPECIFIC":
            n = context.chat_data["episodes"]
            q = context.chat_data["quality"]
            for ep, v in enumerate(videos, start=1):
                await dispatch(ep, [v], [q])
        else:  # MARGE
            n = context.chat_data["episodes"]
            lists = context.chat_data["marge_lists"]
            for ep in range(1, n+1):
                batch = [lists["480p"][ep-1], lists["720p"][ep-1], lists["1080p"][ep-1]]
                await dispatch(ep, batch, ["480p","720p","1080p"])

        for _ in range(3):
            await update.message.reply_text("<b>Main channel : [ @INFI1984 ]</b>", parse_mode="HTML")
        return ConversationHandler.END

    except Exception as e:
        logger.error("Error in receive_details: %s", e)
        await update.message.reply_text(f"❌ {e}\nUse /start")
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Cancelled.")
    return ConversationHandler.END

def main():
    request = Request(connect_timeout=TIMEOUT_CONFIG["connect"], read_timeout=TIMEOUT_CONFIG["read"])
    app = Application.builder().token(BOT_TOKEN).request(request).build()
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_cmd),
            CommandHandler("setsticker", set_sticker_cmd),
            CommandHandler("setformat", set_format_cmd),
            CommandHandler("forepisode", mode_select),
            CommandHandler("forseason", mode_select),
            CommandHandler("forspecificquality", mode_select),
            CommandHandler("formarge", mode_select),
        ],
        states={
            SET_STICKER: [MessageHandler(filters.Sticker.ALL, set_sticker_cmd)],
            SET_FORMAT:  [MessageHandler(filters.Regex("^/setformat "), set_format_cmd)],
            MODE:        [MessageHandler(filters.Regex("^/(forepisode|forseason|forspecificquality|formarge)$"), mode_select)],
            COUNT:       [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_count)],
            VIDEOS:      [MessageHandler(filters.VIDEO | filters.Document.VIDEO, receive_videos)],
            DETAILS:     [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_details)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    logger.info("Starting bot")
    app.run_polling()

if __name__ == "__main__":
    main()
