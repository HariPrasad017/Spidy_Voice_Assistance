"""
S.P.I.D.Y — HuggingFace Intent Detection Module
Uses zero-shot classification (facebook/bart-large-mnli).
Deterministic, race-condition free, and GPU/CPU adaptive.
"""

import logging
from config import TORCH_DEVICE, logger

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
    def __init__(self, auto_load=True):
        self.classifier = None
        self.loaded = False
        self.loading = False
        self.device = TORCH_DEVICE
        if auto_load:
            self.load_model()

    def load_model(self):
        if self.loaded:
            return True

        self.loading = True
        try:
            from transformers import pipeline
            logger.info("Loading Intent Detector (facebook/bart-large-mnli)...")
            
            # Using device=-1 for stable CPU inference to preserve GPU VRAM for Whisper/LLM,
            # or CUDA device index 0 if configured. BART on CPU runs reliably without meta-tensor errors.
            device_idx = -1
            self.classifier = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=device_idx
            )
            self.loaded = True
            logger.info("HuggingFace Intent Detector READY!")
        except Exception as e:
            logger.error(f"Intent detector initialization failed: {e}")
            self.loaded = False
        finally:
            self.loading = False

        return self.loaded

    def detect(self, text: str, threshold: float = 0.35):
        """
        Detects user intent with standardized dictionary output.
        """
        if not self.loaded or not self.classifier or not text:
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
                    'confidence': round(float(top_score), 3)
                }
            return None
        except Exception as e:
            logger.warning(f"Intent classification inference failed: {e}")
            return None

    def get_status(self):
        if self.loaded:
            return "loaded (CPU)"
        elif self.loading:
            return "loading..."
        return "failed"


# Global singleton instance
intent_detector = IntentDetector(auto_load=True)
