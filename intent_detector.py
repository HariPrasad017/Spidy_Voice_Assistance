"""
S.P.I.D.Y — HuggingFace Intent Detection Module
Uses zero-shot classification — no training needed!
"""

from transformers import pipeline
import threading

# ===== INTENT LABELS =====
INTENT_LABELS = [
    "open application",
    "close application", 
    "search the web",
    "play music or video",
    "take screenshot",
    "control volume",
    "control brightness",
    "create folder",
    "get weather information",
    "get news",
    "set reminder or alarm",
    "save note",
    "show notes or reminders",
    "shutdown restart or lock computer",
    "get time or date",
    "coding help or programming",
    "get stock price",
    "tell joke or entertainment",
    "general question or conversation",
    "greet or say hello",
]

# Intent → action mapping
INTENT_ACTIONS = {
    "open application": "open_app",
    "close application": "close_app",
    "search the web": "web_search",
    "play music or video": "play_media",
    "take screenshot": "screenshot",
    "control volume": "volume",
    "control brightness": "brightness",
    "create folder": "create_folder",
    "get weather information": "weather",
    "get news": "news",
    "set reminder or alarm": "reminder",
    "save note": "note",
    "show notes or reminders": "show_data",
    "shutdown restart or lock computer": "power",
    "get time or date": "datetime",
    "coding help or programming": "coding",
    "get stock price": "stock",
    "tell joke or entertainment": "entertainment",
    "general question or conversation": "ai_chat",
    "greet or say hello": "greet",
}

class IntentDetector:
    def __init__(self):
        self.classifier = None
        self.loaded = False
        self.loading = False
        # Load in background thread
        threading.Thread(target=self._load_model, daemon=True).start()

    def _load_model(self):
        self.loading = True
        try:
            print("Loading HuggingFace zero-shot classifier...")
            self.classifier = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=-1  # CPU
            )
            self.loaded = True
            print("HuggingFace Intent Detector: LOADED!")
        except Exception as e:
            print(f"Intent detector load failed: {e}")
            self.loaded = False
        self.loading = False

    def detect(self, text, threshold=0.35):
        """
        Detect intent from user text.
        Returns (intent_label, action, confidence) or None if not confident.
        """
        if not self.loaded or not self.classifier:
            return None

        try:
            result = self.classifier(
                text,
                candidate_labels=INTENT_LABELS,
                multi_label=False
            )
            top_label = result['labels'][0]
            top_score = result['scores'][0]

            if top_score >= threshold:
                action = INTENT_ACTIONS.get(top_label, 'ai_chat')
                return {
                    'intent': top_label,
                    'action': action,
                    'confidence': round(top_score, 3)
                }
            return None
        except Exception as e:
            print(f"Intent detection error: {e}")
            return None

    def get_status(self):
        if self.loaded:
            return "loaded"
        elif self.loading:
            return "loading"
        else:
            return "failed"


# Global instance
intent_detector = IntentDetector()
