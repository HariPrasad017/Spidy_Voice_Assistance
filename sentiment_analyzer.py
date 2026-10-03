"""
S.P.I.D.Y — PyTorch Sentiment Analysis Module
Uses DistilBERT for real-time emotion detection.
Adjusts S.P.I.D.Y response tone based on user mood.
"""

import torch
import logging
from config import TORCH_DEVICE, logger

class SentimentAnalyzer:
    """
    PyTorch-based sentiment analyzer using DistilBERT.
    Detects: POSITIVE, NEGATIVE, NEUTRAL.
    """

    def __init__(self, auto_load=True):
        self.model = None
        self.tokenizer = None
        self.loaded = False
        self.loading = False
        self.device = TORCH_DEVICE if TORCH_DEVICE else torch.device('cpu')
        self.model_name = 'distilbert-base-uncased-finetuned-sst-2-english'

        if auto_load:
            self.load_model()

    def load_model(self):
        """
        Loads the model deterministically onto the designated device.
        """
        if self.loaded:
            return True

        self.loading = True
        try:
            from transformers import DistilBertTokenizer, DistilBertForSequenceClassification
            logger.info(f"Loading Sentiment DistilBERT on {self.device}...")
            self.tokenizer = DistilBertTokenizer.from_pretrained(self.model_name)
            self.model = DistilBertForSequenceClassification.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()
            self.loaded = True
            logger.info(f"PyTorch Sentiment Analyzer READY on {self.device}!")
        except Exception as e:
            logger.error(f"Sentiment Analyzer load failed: {e}")
            self.loaded = False
        finally:
            self.loading = False

        return self.loaded

    def analyze(self, text: str):
        """
        Analyze sentiment of input text.
        Returns dict with label, score, confidence, and tone instruction.
        """
        if not self.loaded or not self.model or not self.tokenizer or not text:
            return {
                'label': 'NEUTRAL',
                'score': 0.5,
                'confidence': 'low',
                'tone': 'normal',
                'loaded': self.loaded
            }

        try:
            inputs = self.tokenizer(
                text,
                return_tensors='pt',
                truncation=True,
                max_length=512,
                padding=True
            ).to(self.device)

            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits

            probs = torch.nn.functional.softmax(logits, dim=-1)
            predicted_class = torch.argmax(probs, dim=1).item()
            confidence_score = probs[0][predicted_class].item()

            label = 'POSITIVE' if predicted_class == 1 else 'NEGATIVE'
            if confidence_score < 0.65:
                label = 'NEUTRAL'

            tone_map = {
                'POSITIVE': 'User is happy and energetic — match their enthusiasm!',
                'NEGATIVE': 'User seems sad or stressed — be extra supportive, encouraging, and gentle.',
                'NEUTRAL': 'User is neutral — be friendly and helpful as usual.'
            }

            return {
                'label': label,
                'score': round(confidence_score, 4),
                'confidence': 'high' if confidence_score > 0.85 else 'medium',
                'tone': tone_map[label],
                'loaded': True,
                'device': str(self.device)
            }
        except Exception as e:
            logger.warning(f"Sentiment analysis inference error: {e}")
            return {
                'label': 'NEUTRAL',
                'score': 0.5,
                'confidence': 'error',
                'tone': 'normal',
                'loaded': self.loaded
            }

    def batch_analyze(self, texts: list):
        if not self.loaded or not texts:
            return []

        try:
            inputs = self.tokenizer(
                texts,
                return_tensors='pt',
                truncation=True,
                max_length=128,
                padding=True
            ).to(self.device)

            with torch.no_grad():
                outputs = self.model(**inputs)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

            results = []
            for i, text in enumerate(texts):
                pred = torch.argmax(probs[i]).item()
                score = probs[i][pred].item()
                label = 'POSITIVE' if pred == 1 else 'NEGATIVE'
                if score < 0.65:
                    label = 'NEUTRAL'
                results.append({'text': text[:50], 'label': label, 'score': round(score, 3)})
            return results
        except Exception as e:
            logger.warning(f"Batch sentiment error: {e}")
            return []

    def get_status(self):
        if self.loaded:
            return f"loaded ({self.device})"
        elif self.loading:
            return "loading..."
        return "failed"


# Global singleton instance
sentiment_analyzer = SentimentAnalyzer(auto_load=True)
