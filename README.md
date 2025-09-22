# Automated FIR Registration System

## Overview
This project is a full-stack Django web application that automates the **FIR (First Information Report) registration process**. It streamlines case management, officer assignment, and police station data handling while integrating **AI/ML models** for FIR classification and IPC section prediction.

## Features
- Full-stack Django web app for FIR filing and management.
- **Multimodal input**:
  - Text (manual entry)
  - Voice (Google Speech-to-Text API)
  - Image/PDF (EasyOCR for extraction)
- **Machine Learning integration**:
  - Random Forest (~85% accuracy) for IPC prediction.
  - TF-IDF, tokenization, clitic handling, and label encoding.
- **NER (Named Entity Recognition)** to extract:
  - People
  - Places
  - Legal terms
- Admin panel for officer assignment and case updates.

## Tech Stack
- **Backend**: Django, Python
- **Frontend**: HTML, CSS, JavaScript
- **Database**: SQLite / PostgreSQL
- **ML Libraries**: scikit-learn, NLTK, spaCy
- **Other Tools**: EasyOCR, Google Speech-to-Text API


