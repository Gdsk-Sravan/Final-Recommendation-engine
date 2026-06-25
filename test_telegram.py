import requests

TOKEN = "8989041075:AAFzW79AjnCXwHv2P_E8frqvNf4xtBHG28Y"
CHAT_ID = "7938909733"

requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    json={
        "chat_id": CHAT_ID,
        "text": "✅ Swing Scanner Telegram Test"
    }
)

print("Sent")
