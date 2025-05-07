# config.py

BOT_TOKEN = '7955582444:AAH3F_Ip8rG6v51Fb7D-jwFEtdrEGfdg0BI'

# Default per-batch qualities
DEFAULT_QUALITIES = ['480p', '720p', '1080p']

# Default HTML caption template
DEFAULT_FORMAT = (
    "<b>[@Rear_Animes]</b> <i>{title} S{season}E{episode} - {quality}</i>\n"
    "<blockquote><b>Join us @Hanime_System</b></blockquote>"
)

# Timeout settings (seconds) to avoid request errors on large batches
TIMEOUT_CONFIG = {
    "connect": 60,
    "read": 300
}
