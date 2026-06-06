"""
S.P.I.D.Y — PyTorch Sentiment Analysis Module
Uses DistilBERT for real-time emotion detection
Adjusts S.P.I.D.Y response tone based on user mood
"""

import torch
import threading
from transformers import DistilBertTokenizer, DistilBertForSequenceClassification

class SentimentAnalyzer:
    """
    PyTorch-based sentiment analyzer using DistilBERT.
    Detects: POSITIVE, NEGATIVE, NEUTRAL
    Adjusts S.P.I.D.Y personality based on user mood.
    """

    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.loaded = False
        self.loading = False
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"PyTorch device: {self.device}")
        # Load in background thread — won't block app startup
        threading.Thread(target=self._load_model, daemon=True).start()

    def _load_model(self):
        self.loading = True
        try:
            print("Loading PyTorch DistilBERT sentiment model...")
            model_name = 'distilbert-base-uncased-finetuned-sst-2-english'
            self.tokenizer = DistilBertTokenizer.from_pretrained(model_name)
            self.model = DistilBertForSequenceClassification.from_pretrained(model_name)
            self.model.to(self.device)
            self.model.eval()  # Set to inference mode
            self.loaded = True
            print(f"PyTorch Sentiment Model LOADED on {self.device}!")
        except Exception as e:
            print(f"Sentiment model load failed: {e}")
            self.loaded = False
        self.loading = False

    def analyze(self, text):
        """
        Analyze sentiment of input text.
        Returns dict with label, score, confidence, and tone_instruction.
        """
        if not self.loaded:
            return {
                'label': 'NEUTRAL',
                'score': 0.5,
                'confidence': 'low',
                'tone': 'normal',
                'loaded': False
            }

        try:
            # Tokenize input
            inputs = self.tokenizer(
                text,
                return_tensors='pt',
                truncation=True,
                max_length=512,
                padding=True
            ).to(self.device)

            # PyTorch inference — no gradient needed
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits

            # Get probabilities using softmax
            probs = torch.nn.functional.softmax(logits, dim=-1)
            predicted_class = torch.argmax(probs, dim=1).item()
            confidence_score = probs[0][predicted_class].item()

            # DistilBERT SST-2: 0=NEGATIVE, 1=POSITIVE
            label = 'POSITIVE' if predicted_class == 1 else 'NEGATIVE'

            # Determine neutral zone
            if confidence_score < 0.65:
                label = 'NEUTRAL'

            # Tone instructions for Groq
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
            print(f"Sentiment analysis error: {e}")
            return {
                'label': 'NEUTRAL',
                'score': 0.5,
                'confidence': 'error',
                'tone': 'normal',
                'loaded': False
            }

    def get_status(self):
        if self.loaded:
            return f"loaded ({self.device})"
        elif self.loading:
            return "loading..."
        else:
            return "failed"

    def batch_analyze(self, texts):
        """
        Analyze multiple texts at once — efficient PyTorch batching.
        Useful for analyzing conversation history.
        """
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
            print(f"Batch sentiment error: {e}")
            return []


# Global instance — loads in background automatically
sentiment_analyzer = SentimentAnalyzer()
