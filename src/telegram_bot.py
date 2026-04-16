import logging
import requests
import threading
import time

class TelegramBot:
    """
    Telegram Bot Interface.
    Handles notifications and commands (via polling).
    """
    def __init__(self, token: str, chat_id: str, enabled: bool = True):
        self.token = token
        self.chat_id = chat_id
        self.enabled = enabled and token != "YOUR_BOT_TOKEN_HERE"
        self.logger = logging.getLogger("IntradaySignals.Telegram")
        self.base_url = f"https://api.telegram.org/bot{token}/"
        self.offset = 0
        self.command_handlers = {}
        
        if self.enabled:
            # Start Polling Thread
            self.stop_event = threading.Event()
            self.poll_thread = threading.Thread(target=self._poll_updates)
            self.poll_thread.daemon = True
            self.poll_thread.start()
            self.send_message("🤖 Intraday Bot Online. Type /help for commands.")

    def register_command(self, command: str, callback):
        """Registers a function to handle a command."""
        self.command_handlers[command] = callback

    def send_message(self, message: str):
        if not self.enabled:
            return
        
        try:
            url = self.base_url + "sendMessage"
            data = {"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"}
            requests.post(url, data=data, timeout=5)
        except Exception as e:
            self.logger.error(f"Failed to send Telegram message: {e}")

    def notify_signal(self, trade):
        """Formats and sends a trade signal."""
        icon = "🟢" if trade['side'] == "BUY" else "🔴"
        msg = (
            f"{icon} *{trade['side']} {trade['symbol']}*\n"
            f"Price: {trade['entry_price']}\n"
            f"Qty: {trade['qty']}\n"
            f"SL: {trade['sl']} | TP: {trade['tp']}\n"
            f"Reason: {trade.get('reason', '')}"
        )
        self.send_message(msg)

    def _poll_updates(self):
        """Polls for new messages/commands."""
        while not self.stop_event.is_set():
            try:
                url = self.base_url + "getUpdates"
                params = {"offset": self.offset + 1, "timeout": 30}
                response = requests.get(url, params=params, timeout=45)
                
                if response.status_code == 200:
                    data = response.json()
                    if data["ok"]:
                        for update in data["result"]:
                            self.offset = update["update_id"]
                            if "message" in update and "text" in update["message"]:
                                text = update["message"]["text"]
                                self._handle_command(text)
            except Exception as e:
                # Suppress ReadTimeout logs as they are expected during polling
                if "Read timed out" in str(e):
                    self.logger.info("Telegram Polling: Read timeout (expected keep-alive).")
                else:
                    self.logger.error(f"Telegram Polling Error: {e}")
                time.sleep(5)
            
            time.sleep(1)

    def _handle_command(self, text: str):
        """Parses and executes commands."""
        parts = text.split()
        if not parts:
            return
        
        cmd = parts[0]
        if cmd in self.command_handlers:
            try:
                response = self.command_handlers[cmd]()
                if response:
                    self.send_message(response)
            except Exception as e:
                self.send_message(f"Error executing command: {e}")
        elif cmd == "/help":
            cmds = "\n".join(self.command_handlers.keys())
            self.send_message(f"Available Commands:\n{cmds}")

    def shutdown(self):
        if self.enabled:
            self.stop_event.set()
